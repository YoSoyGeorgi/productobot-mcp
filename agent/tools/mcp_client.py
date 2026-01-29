import os
import httpx
import json
from typing import Optional
from dotenv import load_dotenv
import openai
from openai import AsyncOpenAI
import logging
from .schema_definitions import SCHEMA_DEFINITIONS
import time

try:
    from ..parallel_config import ENABLE_QUERY_CACHE, QUERY_CACHE_TTL
except Exception:
    ENABLE_QUERY_CACHE = False
    QUERY_CACHE_TTL = 3600

load_dotenv()

logger = logging.getLogger(__name__)
MCP_URL = os.environ.get("MCP_SERVER_URL")

# Store last OpenAI usage metrics per function for diagnostics
OPENAI_USAGE_METRICS: dict = {}

# Simple in-memory caches
_translate_cache = {}  # key -> (timestamp, sql)
_mcp_response_cache = {}  # key -> (timestamp, formatted_response)

# Reusable HTTPX client to avoid TCP/TLS overhead
_httpx_client: Optional[httpx.AsyncClient] = None

async def _get_httpx_client() -> httpx.AsyncClient:
    global _httpx_client
    if _httpx_client is None:
        _httpx_client = httpx.AsyncClient(timeout=30.0)
    return _httpx_client

def _cache_get(cache: dict, key: str):
    if not ENABLE_QUERY_CACHE:
        return None
    entry = cache.get(key)
    if not entry:
        return None
    ts, value = entry
    if time.time() - ts > QUERY_CACHE_TTL:
        try:
            del cache[key]
        except KeyError:
            pass
        return None
    return value

def _cache_set(cache: dict, key: str, value):
    if not ENABLE_QUERY_CACHE:
        return
    cache[key] = (time.time(), value)

class MCPClientError(Exception):
    pass

async def translate_nl_to_sql(prompt: str, schema_info: str = "", history: list = None) -> str:
    """Use OpenAI to translate natural language to SQL"""
    # Check cache first
    cache_key = f"translate:{prompt}:{schema_info}"
    cached = _cache_get(_translate_cache, cache_key)
    if cached:
        return cached

    client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    system_prompt = f"""Eres un experto en SQL y bases de datos de Supabase. 
Convierte preguntas en español a consultas SQL de PostgreSQL.
La base de datos tiene tablas para experiencias turísticas, alojamientos y transportes.

{schema_info}

REGLAS IMPORTANTES:
1. NUNCA incluyas columnas de vectores/embeddings en el SELECT (vector_embedding, embeddings, embedding, full_json, etc.)
2. Primero revisa el esquema para saber qué columnas existen en cada tabla.
3. Para la tabla 'experiences', SIEMPRE intenta obtener el precio haciendo un LEFT JOIN con 'tariff_person_group' usando 'supplier_name'.
   Ejemplo: SELECT e.id, e.narrative_text, e.service_type, e.city, e.supplier_name, e.destination_name, e.duration, t.sellfits as price 
   FROM experiences e 
   LEFT JOIN tariff_person_group t ON e.supplier_name = t.supplier_name
4. IMPORTANTE: Las tablas 'lodging', 'experiences' y 'transport' NO tienen columna 'is_deleted'. NO la incluyas en el WHERE.
5. Usa ILIKE con '%término%' para búsquedas de texto.
6. Para nombres de lugares compuestos (ej. "Xpu Ha"), reemplaza los espacios con '%' en la búsqueda (ej. '%Xpu%Ha%') para encontrar variaciones con guiones o espacios.
7. Si la consulta es sobre alojamientos o transporte, aplica la misma lógica de precios si es posible, o busca en sus tablas respectivas.

Responde SOLO con la consulta SQL, sin explicaciones ni formato markdown."""

    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation history if available to maintain context
    if history:
        # Filter and format history messages
        # We only want user and assistant text messages
        for msg in history:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                # Limit content length to avoid token limits
                content = str(msg["content"])[:500]
                messages.append({"role": msg["role"], "content": content})

    messages.append({"role": "user", "content": prompt})

    response = await client.chat.completions.create(
        model="gpt-4.1-mini-2025-04-14",
        messages=messages,
        temperature=0
    )
    
    # Log token usage if available
    try:
        usage = None
        # response.usage may be a dict or an object
        if hasattr(response, "usage"):
            usage = response.usage
        elif isinstance(response, dict):
            usage = response.get("usage")

        if usage:
            # Access fields safely
            prompt_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else getattr(usage, "prompt_tokens", None)
            completion_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else getattr(usage, "completion_tokens", None)
            total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else getattr(usage, "total_tokens", None)
            # Compute a fallback total if the field is not present
            computed_total = total_tokens if total_tokens is not None else ((prompt_tokens or 0) + (completion_tokens or 0))
            log_msg = f"OpenAI token usage (translate_nl_to_sql): prompt={prompt_tokens} completion={completion_tokens} total={computed_total}"
            logger.info(log_msg)
            # Print full message and an explicit total-only line for quick visibility
            print(f"[OpenAI usage] translate_nl_to_sql: {log_msg}")
            print(f"[OpenAI usage] translate_nl_to_sql: total_tokens={computed_total}")

            # Save metrics for aggregation later in the MCP flow
            try:
                OPENAI_USAGE_METRICS['translate_nl_to_sql'] = {
                    'prompt_tokens': int(prompt_tokens or 0),
                    'completion_tokens': int(completion_tokens or 0),
                    'total_tokens': int(computed_total or 0)
                }
            except Exception:
                logger.debug("Failed to store translate_nl_to_sql usage metric")
        else:
            logger.info("OpenAI response contains no usage information")
            print("[OpenAI usage] translate_nl_to_sql: no usage info available")
    except Exception as e:
        logger.warning(f"Failed to log OpenAI usage: {e}")

    sql = response.choices[0].message.content.strip()
    # Remove markdown code blocks if present
    sql = sql.replace("```sql", "").replace("```", "").strip()
    # Store in cache
    try:
        _cache_set(_translate_cache, cache_key, sql)
    except Exception:
        pass
    return sql


async def format_results_with_openai(original_query: str, results: list) -> str:
    """Format SQL results into natural language using OpenAI."""
    client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    # Limit data sent to OpenAI to avoid token limits
    limited_results = results[:10]  # Max 10 results
    
    system_prompt = """Eres un asistente turístico amigable de ProductoBot. Tu tarea es presentar información de productos/experiencias turísticas de manera natural y útil.

Reglas:
- Responde en español natural y conversacional
- Destaca lo más importante: nombre, ubicación, descripción breve, precios si están disponibles
- Usa emojis relevantes (🏨 🍽️ 🎭 🏞️ etc.) para hacer la respuesta más atractiva
- Agrupa información similar
- No menciones campos técnicos (id, json, embeddings, etc.)
- Si hay muchos resultados, menciona los destacados y resume el resto
- Mantén un tono profesional pero cercano"""
    
    user_prompt = f"""El usuario preguntó: "{original_query}"

Los resultados de la base de datos son:
{json.dumps(limited_results, ensure_ascii=False, indent=2)}

{"Nota: Solo se muestran los primeros 10 de " + str(len(results)) + " resultados." if len(results) > 10 else ""}

Presenta esta información de forma natural y útil para el usuario."""
    
    response = await client.chat.completions.create(
        model="gpt-4.1-mini-2025-04-14",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7,
        max_tokens=1000
    )

    # Log token usage if available
    try:
        usage = None
        if hasattr(response, "usage"):
            usage = response.usage
        elif isinstance(response, dict):
            usage = response.get("usage")

        if usage:
            prompt_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else getattr(usage, "prompt_tokens", None)
            completion_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else getattr(usage, "completion_tokens", None)
            total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else getattr(usage, "total_tokens", None)
            computed_total = total_tokens if total_tokens is not None else ((prompt_tokens or 0) + (completion_tokens or 0))
            log_msg = f"OpenAI token usage (format_results_with_openai): prompt={prompt_tokens} completion={completion_tokens} total={computed_total}"
            logger.info(log_msg)
            print(f"[OpenAI usage] format_results_with_openai: {log_msg}")
            print(f"[OpenAI usage] format_results_with_openai: total_tokens={computed_total}")

            # Save metrics for aggregation later
            try:
                OPENAI_USAGE_METRICS['format_results_with_openai'] = {
                    'prompt_tokens': int(prompt_tokens or 0),
                    'completion_tokens': int(completion_tokens or 0),
                    'total_tokens': int(computed_total or 0)
                }
            except Exception:
                logger.debug("Failed to store format_results_with_openai usage metric")
        else:
            logger.info("OpenAI response contains no usage information")
            print("[OpenAI usage] format_results_with_openai: no usage info available")
    except Exception as e:
        logger.warning(f"Failed to log OpenAI usage: {e}")

    return response.choices[0].message.content.strip()

async def mcp_query_nl_to_sql(prompt: str, access_token: Optional[str] = None, history: list = None) -> str:
    """
    Sends a minimal MCP JSON-RPC initialize followed by a basic completion request
    to an HTTP MCP server. Returns the textual response if available.

    Note: This is a lightweight client for Supabase MCP HTTP transport. It expects
    servers that support JSON-RPC over HTTP with the MCP headers.
    """
    if not MCP_URL:
        raise MCPClientError("MCP_SERVER_URL not configured")

    # Clear per-call OpenAI usage metrics
    try:
        OPENAI_USAGE_METRICS.clear()
    except Exception:
        pass

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-06-18",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    client = await _get_httpx_client()

    # Initialize session
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"elicitation": {}},
            "clientInfo": {
                "name": "productobot-slack",
                "title": "ProductoBot Slack MCP Client",
                "version": "0.1.0",
            },
        },
    }
    init_resp = await client.post(MCP_URL, headers=headers, content=json.dumps(init_payload))
    if init_resp.status_code >= 300:
        raise MCPClientError(f"MCP initialize failed: {init_resp.status_code} {init_resp.text}")

    # Extract session ID from response headers
    session_id = init_resp.headers.get("Mcp-Session-Id")
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    # List available tools to find the right one for natural language
    list_tools_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
    }
    tools_resp = await client.post(MCP_URL, headers=headers, content=json.dumps(list_tools_payload))
    if tools_resp.status_code >= 300:
        raise MCPClientError(f"MCP tools/list failed: {tools_resp.status_code} {tools_resp.text}")

    tools_data = tools_resp.json()
    # Log available tools for debugging
    import logging
    logger = logging.getLogger(__name__)

    # Use the provided schema definitions
    schema_info = SCHEMA_DEFINITIONS

    # Translate natural language to SQL using OpenAI
    logger.info(f"Translating query: {prompt}")
    sql_query = await translate_nl_to_sql(prompt, schema_info, history)
    logger.info(f"Generated SQL: {sql_query}")

    # Check cached formatted response for this SQL
    cache_key = f"mcp_sql:{sql_query}"
    cached_response = _cache_get(_mcp_response_cache, cache_key)
    if cached_response:
        logger.info("Returning cached MCP response")
        return cached_response

    # Call execute_sql with the generated SQL
    call_tool_payload = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "execute_sql",
            "arguments": {
                "query": sql_query
            }
        }
    }
    tool_resp = await client.post(MCP_URL, headers=headers, content=json.dumps(call_tool_payload))
    if tool_resp.status_code >= 300:
        raise MCPClientError(f"MCP tools/call failed: {tool_resp.status_code} {tool_resp.text}")

    data = tool_resp.json()
    # Extract text content from MCP tool response
    result = data.get("result") or {}
    content = result.get("content") or []

    # MCP tools return content array with text/image/resource items
    text_parts = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
            text_parts.append(part["text"])

    if text_parts:
        raw_response = "\n".join(text_parts)

        # Check for error responses from Supabase/Postgres
        if '{"error":' in raw_response or "Failed to run sql query" in raw_response:
            logger.warning(f"MCP returned an SQL execution error: {raw_response[:200]}")
            return None

        # Check if response indicates no results
        # Supabase MCP often returns "[]" inside untrusted-data tags or just "[]"
        if "[]" in raw_response or "no data" in raw_response.lower():
            # Double check if it's really empty by looking for non-empty JSON arrays
            # If we see "[{" or similar, it might have data. But "[]" usually means empty.
            # A simple heuristic: if "[]" is present and we don't see "[{" or "{\"", it's likely empty.
            if "[{" not in raw_response and "{\"" not in raw_response:
                logger.info("MCP returned empty results (found '[]' and no objects)")
                return None

        # Use OpenAI to parse and format the response
        # This handles the untrusted-data format and extracts meaningful info
        logger.info("Using OpenAI to extract and format results from MCP response")
        logger.info(f"Raw response preview (first 1000 chars): {raw_response[:1000]}")

        client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        system_prompt = """Eres un asistente turístico de ProductoBot. Recibirás una respuesta de base de datos que contiene información de productos turísticos en formato JSON (posiblemente dentro de bloques <untrusted-data>).

Tu tarea es:
1. Extraer la información relevante del JSON
2. Presentarla de forma CONCISA en español (máximo 2500 caracteres total)
3. **IMPORTANTE: Si hay muchos resultados (más de 5), muestra solo los primeros 5 y menciona cuántos hay en total**
4. Para cada resultado: nombre, ubicación breve, descripción corta (1-2 líneas), duración, precio
5. Usar emojis relevantes pero con moderación (🚗 🏨 🍽️ 🎭 🏞️ 💰 ⏱️)
6. No mencionar campos técnicos (id, embeddings, json, etc.)
7. Formato: Lista numerada, cada item máximo 3-4 líneas"""

        user_prompt = f"""El usuario preguntó: "{prompt}"

Respuesta completa de la base de datos:
{raw_response[:15000]}

INSTRUCCIONES CRÍTICAS:
1. Busca los objetos JSON en la respuesta (dentro de bloques <untrusted-data> o arrays)
2. Si hay más de 5 resultados, muestra SOLO los primeros 5 y agrega: "_(Y X resultados más...)_"
3. Por cada resultado: nombre, ubicación breve, descripción corta, duración, precio
4. Mantén cada item en 3-4 líneas máximo
5. NO digas "no hay resultados" si ves datos JSON
6. Respuesta total: máximo 2500 caracteres"""

        response = await client.chat.completions.create(
            model="gpt-4.1-mini-2025-04-14",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )

        formatted_response = response.choices[0].message.content.strip()
        logger.info(f"Formatted response: {formatted_response[:150]}...")

        # Cache formatted response for this SQL
        try:
            _cache_set(_mcp_response_cache, cache_key, formatted_response)
        except Exception:
            pass

        # Aggregate and print OpenAI usage metrics for this MCP flow
        try:
            total_sum = 0
            breakdown = []
            for k, v in OPENAI_USAGE_METRICS.items():
                t = int(v.get('total_tokens', (v.get('prompt_tokens', 0) + v.get('completion_tokens', 0))))
                total_sum += t
                breakdown.append(f"{k}={t}")
            if breakdown:
                agg_msg = f"Total OpenAI tokens for MCP flow: {total_sum} ({', '.join(breakdown)})"
            else:
                agg_msg = "Total OpenAI tokens for MCP flow: no token metrics available"
            logger.info(agg_msg)
            print(f"[OpenAI usage] MCP flow: {agg_msg}")
        except Exception as e:
            logger.debug(f"Failed to aggregate OpenAI usage metrics: {e}")

        return formatted_response

    # Last resort: stringify full response
    return json.dumps(data, ensure_ascii=False)
