# Parallel Agents Implementation - ProductoBot

## Overview

Se ha integrado el patrón de **agentes paralelos** del OpenAI Cookbook en ProductoBot para mejorar significativamente el rendimiento en consultas multi-dominio.

### ¿Por qué agentes paralelos?

Muchas consultas de usuarios involucran múltiples dominios independientes:
- **Query**: "Dame un hotel en Cancún, tours de snorkel y cómo llegar"
- **Dominios**: Alojamiento + Experiencias + Transporte

**Sin parallelización**: Ejecutar secuencialmente = ~90 segundos (30s + 30s + 30s)
**Con parallelización**: Ejecutar simultáneamente = ~35 segundos (max de los tres)

## Arquitectura

### 1. **Specialized Agents** (`ruto_agent.py`)

Cuatro agentes especializados, cada uno enfocado en un dominio:

```python
experiences_agent  → Actividades, tours, experiencias
lodging_agent     → Hoteles, cabañas, alojamientos
transportation_agent → Transporte, transfers, rutas
database_agent    → Consultas específicas de datos
```

**Ventajas**:
- Agentes más pequeños y enfocados
- Instrucciones específicas por dominio
- Mejor manejo de contexto

### 2. **ParallelAgentRunner** (`parallel_agents.py`)

Ejecuta múltiples agentes concurrentemente usando `asyncio.gather()`:

```python
# Pseudocódigo
results = await asyncio.gather(
    run_agent(experiences_agent, query),
    run_agent(lodging_agent, query),
    run_agent(transportation_agent, query),
    run_agent(database_agent, query)
)

# Meta-agent combina los resultados
final_response = await meta_agent(combine(results))
```

**Características**:
- ✅ Ejecución concurrente verdadera
- ✅ Tracking de tiempos de ejecución
- ✅ Manejo de errores individual por agente
- ✅ Fallback automático

### 3. **HybridAgentOrchestrator** (`parallel_agents.py`)

Decide automáticamente si usar ejecución paralela o secuencial:

```python
analysis = await analyzer.analyze_query(query)

if analysis["should_parallelize"] and len(domains) > 1:
    # Usar agentes paralelos
    response = await parallel_runner.run_parallel(query)
else:
    # Usar agente ReAct secuencial
    response = await single_agent.run(query)
```

**Lógica de decisión**:
- `should_parallelize = true` si la query involucra 2+ dominios
- `domains` = lista de dominios detectados
- `complexity` = "simple", "moderate" o "complex"

### 4. **Meta-Agent**

Combina los resultados de los agentes especializados en una respuesta coherente:

```
Entrada:
  ### ExperiencesAgent
  Recomendamos: Buceo en cenotes, tours a Chichen Itza...
  
  ### LodgingAgent  
  Hoteles recomendados: Grand Palladium, Moon Palace...
  
  ### TransportationAgent
  Transfer desde aeropuerto: $45 por persona...

Salida (Meta-Agent):
  "Para tu viaje a Cancún recomendamos:
   
   🏨 Alojamiento: Grand Palladium (5 estrellas, $350/noche)
   
   🤿 Experiencias: Tours de buceo en cenotes (9am, $65)
   
   🚐 Transporte: Transfer desde aeropuerto ($45)"
```

## Archivos Añadidos/Modificados

### Nuevos Archivos

#### `parallel_agents.py`
- `ParallelAgentRunner`: Ejecutor de agentes paralelos
- `HybridAgentOrchestrator`: Analizador y orquestador de estrategia
- `UserInfoContext`: Contexto compartido
- `create_parallel_agents_from_tools()`: Factory para crear agentes

#### `demo_parallel_agents.py`
- Ejemplos de uso
- Benchmark de rendimiento
- Demostración de casos de uso

### Archivos Modificados

#### `ruto_agent.py`
```python
# Nuevas importaciones
from parallel_agents import ParallelAgentRunner, HybridAgentOrchestrator

# Nuevos agentes especializados
experiences_agent      # Extrae dominio de experiencias
lodging_agent         # Extrae dominio de alojamiento
transportation_agent  # Extrae dominio de transporte
database_agent        # Extrae dominio de datos
meta_agent            # Combina resultados

# Nuevas utilidades
parallel_runner       # ParallelAgentRunner
hybrid_orchestrator   # HybridAgentOrchestrator
query_analyzer        # Analyzes query complexity

# Función actualizada
async def chat(..., use_parallel=True):
    # Ahora soporta ejecución paralela
    if use_parallel:
        response = await hybrid_orchestrator.process(query, context)
    else:
        response = await runner.run(productobot_agent, query)
```

## Uso

### En Código
```python
# Habilitar agentes paralelos (por defecto)
response = await chat(
    query="Quiero un hotel en Cancún y tours de buceo",
    first_name="María",
    use_parallel=True  # Automáticamente detecta multi-dominio
)

# Forzar ejecución secuencial si es necesario
response = await chat(
    query=query,
    first_name="Carlos",
    use_parallel=False
)
```

### En Slack
Sin cambios - la integración de Slack en `app.py` continúa igual:
```python
from ruto_agent import chat

response = await chat(
    query=message,
    channel_id=channel,
    thread_ts=thread_ts,
    first_name=user_name
)
```

El parámetro `use_parallel=True` es el default, así que automáticamente beneficia todas las queries.

## Flujo de Ejecución

### Consulta Multi-Dominio (Paralela)

```
┌─ "Dame hotel en Cancún, buceo y transporte"
│
├─ HybridOrchestrator.process()
│  └─ analyze_query() → {should_parallelize: true, domains: [lodging, experiences, transport]}
│
├─ ParallelAgentRunner.run_parallel()
│  │
│  ├─ [Paralelo] ExperiencesAgent → "Buceo en cenotes..."
│  ├─ [Paralelo] LodgingAgent → "Hoteles: Grand Palladium..."
│  ├─ [Paralelo] TransportationAgent → "Transfer desde airport..."
│  │
│  └─ MetaAgent(combine results) → "Respuesta integrada"
│
└─ Response: "Para tu viaje recomendamos: ..."
  (Total: ~35s en lugar de ~90s)
```

### Consulta Simple (Secuencial)

```
┌─ "¿Hoteles en Playa del Carmen?"
│
├─ HybridOrchestrator.process()
│  └─ analyze_query() → {should_parallelize: false, domains: [lodging]}
│
├─ ProductoBotAgent.run() [ReAct Loop]
│  ├─ Thought: Usuario pregunta por hoteles
│  ├─ Action: Usar get_lodging()
│  ├─ Observation: [results]
│  └─ Final Answer: "Hoteles recomendados..."
│
└─ Response: "Encontré 5 hoteles en Playa del Carmen..."
  (Total: ~30s - eficiente para queries simples)
```

## Beneficios

| Aspecto | Antes | Después |
|--------|-------|---------|
| **Multi-dominio** | ~90s | ~35s ⚡ |
| **Single-dominio** | ~30s | ~30s (sin overhead) |
| **Complejidad** | 1 gran agente | 4 especializados + meta |
| **Escalabilidad** | Difícil de extender | Fácil agregar nuevos dominios |
| **Latencia P95** | Variable | Previsible (max del 90th percentile) |
| **Costo** | 1 prompt análisis | +1 meta-agent call (5-10% extra) |

## Configuración y Ajustes

### Agregar Nuevo Dominio

1. Crear agente especializado:
```python
my_domain_agent = Agent(
    name="MyDomainAgent",
    instructions="Focus on my domain...",
    tools=[my_tool]
)
```

2. Agregar a `parallel_agents_list`:
```python
parallel_agents_list = [
    (experiences_agent, "Experiences"),
    (lodging_agent, "Lodging"),
    (my_domain_agent, "My Domain"),  # ← Nuevo
]
```

3. Meta-agent automáticamente lo incluirá.

### Ajustar Threshold de Paralelización

En `parallel_agents.py`, modificar `analyze_query()`:

```python
# Actual: threshold es 2 dominios
if len(found_domains) > 1:
    should_parallelize = True

# Modificar a 3 dominios para ser más selectivo:
if len(found_domains) > 2:
    should_parallelize = True
```

### Modelos y Costos

Actual:
- Main agent: `gpt-4-mini` (por defecto)
- Parallel agents: `gpt-4-mini`
- Meta-agent: `gpt-4-mini`

Para optimizar costos, se puede ajustar:
```python
# Usar modelo más barato para agentes especializados
experiences_agent = Agent(..., model="gpt-3.5-turbo")
```

## Troubleshooting

### Problema: Parallel execution cae a fallback

**Causa**: Error en uno de los agentes paralelos.
**Solución**: Ver logs - agentes individuales loguean sus errores:
```
WARNING: ExperiencesAgent: [error message]
INFO: Falling back to sequential execution
```

### Problema: Meta-agent produce respuesta desconectada

**Causa**: Instrucciones del meta-agent no claras.
**Solución**: Refinar instrucciones en el meta-agent:
```python
meta_agent = Agent(
    instructions="Específicamente: integra resultados, destaca conexiones..."
)
```

### Problema: Queries simples son más lentas que antes

**Causa**: Overhead del análisis de query.
**Solución**: El orchestrator detecta queries simples y usa agent único (sin overhead extra).

## Testing

```bash
# Demo interactivo
python agent/demo_parallel_agents.py

# En CLI productoBotAgent
python agent/ruto_agent.py
```

## Futuras Mejoras

1. **Caché de análisis de query**: Guardar análisis comunes
2. **Timeout adaptativo**: Ajustar timeouts según latencia histórica
3. **Weighted queries**: Priorizar agentes rápidos si el resultado es bueno
4. **Streaming**: Output incremental del meta-agent mientras otros agentes aún procesan
5. **A/B Testing**: Comparar paralelo vs secuencial para diferentes queries

## Referencias

- [OpenAI Cookbook: Parallel Agents](https://cookbook.openai.com/examples/agents_sdk/parallel_agents)
- [Agents SDK Documentation](https://openai.github.io/openai-agents-python/)
- [asyncio Documentation](https://docs.python.org/3/library/asyncio.html)
