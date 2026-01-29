import asyncio
import os
import time
import json
import logging
from dotenv import load_dotenv
from pathlib import Path
import sys
from openai import OpenAI

# Load environment variables
load_dotenv()

# Add the agent directory to sys.path
agent_path = Path(__file__).parent / "agent"
sys.path.append(str(agent_path))

from agent.ruto_agent import productobot_agent, UserInfoContext
from agents import Runner, ItemHelpers, MessageOutputItem

# Set up logging to a file to keep console clean
logging.basicConfig(
    filename='benchmark.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize OpenAI client for grading
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

QUERIES = {
    "transports": [
        "¿Cómo llego de CDMX a Oaxaca?",
        "Busco transporte compartido de San Cristóbal a Palenque",
        "Transporte privado del aeropuerto de Cancún a Tulum",
        "¿Hay camiones de Mérida a Valladolid?",
        "Mejor forma de ir de Puerto Escondido a Mazunte",
        "Precio de un taxi del centro al aeropuerto de Guadalajara",
        "¿Cómo viajar de Ciudad de México a Puebla de forma barata?",
        "Transporte de Holbox a Chiquilá",
        "Van de Playa del Carmen a Tulum",
        "¿Hay ferries de Cozumel a Playa del Carmen?"
    ],
    "experiences": [
        "Tours de senderismo en el Volcán Paricutín",
        "Clase de cocina tradicional en Oaxaca",
        "Tour de avistamiento de ballenas en Baja California",
        "Experiencia de buceo en Cozumel",
        "Caminata por la selva en Palenque",
        "Tour de mezcal en Santiago Matatlán",
        "Clase de surf en Sayulita",
        "Tour de cenotes en Valladolid",
        "Experiencia de observación de aves en Celestún",
        "Tour gastronómico en la Ciudad de México"
    ],
    "lodging": [
        "Hoteles baratos en el centro de San Miguel de Allende",
        "Cabañas sustentables en la Sierra Gorda",
        "Hostales cerca de la playa en Puerto Escondido",
        "Hotel con vista al mar en Mazatlán",
        "Donde hospedarse en Real de Catorce",
        "Alojamientos pet-friendly en Valle de Bravo",
        "Hoteles boutique en Mérida",
        "Cabañas en el bosque en Mazamitla",
        "Hospedaje económico en San Cristóbal de las Casas",
        "Hotel todo incluido en Puerto Vallarta"
    ]
}

async def grade_response(query, response):
    try:
        prompt = f"""
        Evalúa la siguiente respuesta de un asistente de viajes (ProductoBot) para la agencia Rutopía.
        Escala: 0 a 10.
        Criterios:
        1. ¿Responde directamente a lo que el usuario pidió?
        2. ¿La información es relevante y útil?
        3. ¿El tono es amable y profesional?
        4. ¿Usa formato Slack (* para negritas, • para listas)?
        
        Usuario: {query}
        ProductoBot: {response}
        
        Responde ÚNICAMENTE con el número de la calificación (ej. 8.5 o 9).
        """
        
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Eres un auditor de calidad de servicio al cliente."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        grade_str = completion.choices[0].message.content.strip()
        return float(grade_str)
    except Exception as e:
        logger.error(f"Error grading response: {e}")
        return 0.0

async def run_benchmark():
    results = []
    
    print(f"Starting benchmark: 3 categories, 10 queries each. Total 30 runs.")
    
    for category, queries in QUERIES.items():
        print(f"\nTesting category: {category}")
        for i, query in enumerate(queries):
            print(f"  Run {i+1}/10: {query[:50]}...", end="", flush=True)
            
            context = UserInfoContext(first_name="Benchmarker")
            input_items = [{"content": query, "role": "user"}]
            
            start_time = time.time()
            try:
                result = await Runner.run(productobot_agent, input_items, context=context)
                duration = time.time() - start_time
                
                # Extract response text
                response_text = ""
                for new_item in result.new_items:
                    if isinstance(new_item, MessageOutputItem):
                        text = ItemHelpers.text_message_output(new_item)
                        if text:
                            response_text += text + "\n"
                
                # Extract tokens
                total_tokens = 0
                if hasattr(result, 'raw_responses'):
                    for resp in result.raw_responses:
                        if hasattr(resp, 'usage') and resp.usage:
                            total_tokens += resp.usage.total_tokens
                
                # Extract routes (tool calls)
                tools_used = []
                for item in result.new_items:
                    if "ToolCall" in type(item).__name__ and not "Output" in type(item).__name__:
                        if hasattr(item, 'raw_item') and hasattr(item.raw_item, 'name'):
                            tools_used.append(item.raw_item.name)
                
                # Grade
                grade = await grade_response(query, response_text)
                
                run_data = {
                    "category": category,
                    "query": query,
                    "response": response_text.strip(),
                    "tokens_spent": total_tokens,
                    "execution_time": round(duration, 2),
                    "grade": grade,
                    "route": ", ".join(tools_used) if tools_used else "None (Direct response)"
                }
                results.append(run_data)
                print(f" Done. (Grade: {grade}, Time: {duration:.1f}s)")
                
            except Exception as e:
                print(f" Error: {e}")
                logger.error(f"Error in run {category} {i}: {e}")
                results.append({
                    "category": category,
                    "query": query,
                    "error": str(e)
                })

    # Save results
    output_file = "benchmark_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    
    print(f"\nBenchmark complete. Results saved to {output_file}")
    
    # Summary
    print("\nSummary:")
    for cat in QUERIES.keys():
        cat_results = [r for r in results if r.get("category") == cat and "error" not in r]
        if cat_results:
            avg_grade = sum(r["grade"] for r in cat_results) / len(cat_results)
            avg_time = sum(r["execution_time"] for r in cat_results) / len(cat_results)
            avg_tokens = sum(r["tokens_spent"] for r in cat_results) / len(cat_results)
            print(f"- {cat.capitalize()}: Avg Grade: {avg_grade:.2f}, Avg Time: {avg_time:.2f}s, Avg Tokens: {avg_tokens:.0f}")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
