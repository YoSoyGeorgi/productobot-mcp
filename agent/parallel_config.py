"""
Configuration for Parallel Agents
Centralized settings for tuning parallel execution behavior
"""

import os
from typing import Dict, List, Literal

# ===== EXECUTION STRATEGY =====
# Enable/disable parallel agent execution
ENABLE_PARALLEL_AGENTS = os.environ.get("ENABLE_PARALLEL_AGENTS", "true").lower() == "true"

# Minimum number of domains to trigger parallel execution
# Set to 4+ to avoid parallelization overhead (parallel only faster with truly complex queries)
MIN_DOMAINS_FOR_PARALLEL = int(os.environ.get("MIN_DOMAINS_FOR_PARALLEL", "4"))

# Maximum time to wait for any parallel agent before giving up (seconds)
# Increased to 60s to let agents complete properly
PARALLEL_EXECUTION_TIMEOUT = int(os.environ.get("PARALLEL_EXECUTION_TIMEOUT", "60"))

# ===== AGENT MODELS =====
# Models used for each agent type
AGENT_MODELS = {
    "main_agent": os.environ.get("MAIN_AGENT_MODEL", "gpt-4.1-mini-2025-04-14"),
    "specialized_agents": os.environ.get("SPECIALIZED_AGENTS_MODEL", "gpt-4.1-mini-2025-04-14"),
    "meta_agent": os.environ.get("META_AGENT_MODEL", "gpt-4.1-mini-2025-04-14"),
    "query_analyzer": os.environ.get("QUERY_ANALYZER_MODEL", "gpt-4.1-mini-2025-04-14"),
}

# ===== PERFORMANCE TUNING =====
# Enable execution timeline logging for debugging
LOG_EXECUTION_TIMELINE = os.environ.get("LOG_EXECUTION_TIMELINE", "false").lower() == "true"

# Enable detailed agent-level logging
DEBUG_AGENT_EXECUTION = os.environ.get("DEBUG_AGENT_EXECUTION", "false").lower() == "true"

# ===== QUERY DETECTION =====
# Keywords for detecting specific domains in user queries
DOMAIN_KEYWORDS = {
    "experiences": [
        "actividad", "actividades", "experiencia", "experiencias",
        "tour", "tours", "visita", "visitas", "excursión", "excursiones",
        "buceo", "senderismo", "rafting", "aventura", "aventuras",
        "qué hacer", "qué ver", "ver", "visitar"
    ],
    "lodging": [
        "hotel", "hoteles", "alojamiento", "alojamientos",
        "hospedaje", "cabaña", "cabañas", "resort", "resorts",
        "hostia", "hostal", "hostelería",
        "dónde dormir", "dónde quedarme", "dónde hospedarse",
        "habitación", "cuarto"
    ],
    "transportation": [
        "transporte", "transportes", "transfer", "transfers",
        "ruta", "rutas", "cómo llegar", "cómo ir",
        "vuelo", "vuelos", "avión", "autobús", "bus",
        "taxi", "Uber", "carro", "auto", "coche",
        "llegada", "salida", "desplazamiento"
    ],
    "database": [
        "disponibilidad", "disponible", "cuándo", "fechas",
        "precio", "precios", "costo", "costos",
        "información", "detalles", "especificaciones",
        "buscar", "búsqueda", "filter", "filtro"
    ]
}

# ===== AGENT DESCRIPTIONS =====
# Descriptions used in parallel_agents_list
AGENT_DESCRIPTIONS = {
    "experiences": "Experiences and activities",
    "lodging": "Accommodation options",
    "transportation": "Transportation logistics",
    "database": "Specific data lookups"
}

# ===== FALLBACK BEHAVIOR =====
# If parallel execution fails, automatically fallback to sequential
FALLBACK_TO_SEQUENTIAL = os.environ.get("FALLBACK_TO_SEQUENTIAL", "true").lower() == "true"

# Maximum retries for individual parallel agents
MAX_AGENT_RETRIES = int(os.environ.get("MAX_AGENT_RETRIES", "1"))

# ===== CACHING =====
# Enable query analysis caching (experimental)
ENABLE_QUERY_CACHE = os.environ.get("ENABLE_QUERY_CACHE", "false").lower() == "true"

# TTL for query cache in seconds (3600 = 1 hour)
QUERY_CACHE_TTL = int(os.environ.get("QUERY_CACHE_TTL", "3600"))

# ===== RESPONSE FORMATTING =====
# Include execution time information in responses
INCLUDE_TIMING_INFO = os.environ.get("INCLUDE_TIMING_INFO", "false").lower() == "true"

# Include agent names in response
INCLUDE_AGENT_ATTRIBUTION = os.environ.get("INCLUDE_AGENT_ATTRIBUTION", "true").lower() == "true"

# ===== UTILITY FUNCTIONS =====

def get_enabled_domains() -> List[str]:
    """Get list of domains that should be checked for parallelization"""
    domains = []
    if os.environ.get("ENABLE_EXPERIENCES_AGENT", "true").lower() == "true":
        domains.append("experiences")
    if os.environ.get("ENABLE_LODGING_AGENT", "true").lower() == "true":
        domains.append("lodging")
    if os.environ.get("ENABLE_TRANSPORTATION_AGENT", "true").lower() == "true":
        domains.append("transportation")
    if os.environ.get("ENABLE_DATABASE_AGENT", "true").lower() == "true":
        domains.append("database")
    return domains

def detect_domains(query: str) -> List[str]:
    """
    Detect which domains are mentioned in a query
    Returns: List of domain names detected
    """
    query_lower = query.lower()
    detected = []
    
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(keyword in query_lower for keyword in keywords):
            detected.append(domain)
    
    return detected

def should_use_parallel(detected_domains: List[str]) -> bool:
    """
    Determine if parallel execution should be used
    based on number of detected domains
    """
    if not ENABLE_PARALLEL_AGENTS:
        return False
    
    return len(detected_domains) >= MIN_DOMAINS_FOR_PARALLEL

# ===== LOGGING CONFIGURATION =====

LOG_CONFIG = {
    "parallel_agents.enable": ENABLE_PARALLEL_AGENTS,
    "parallel_agents.min_domains": MIN_DOMAINS_FOR_PARALLEL,
    "parallel_agents.timeout": PARALLEL_EXECUTION_TIMEOUT,
    "debug": DEBUG_AGENT_EXECUTION,
    "execution_timeline": LOG_EXECUTION_TIMELINE,
}

def print_config():
    """Print current configuration"""
    print("\n" + "="*60)
    print("Parallel Agents Configuration")
    print("="*60)
    print(f"Enabled: {ENABLE_PARALLEL_AGENTS}")
    print(f"Min domains for parallel: {MIN_DOMAINS_FOR_PARALLEL}")
    print(f"Timeout: {PARALLEL_EXECUTION_TIMEOUT}s")
    print(f"Models: {AGENT_MODELS}")
    print(f"Enabled domains: {get_enabled_domains()}")
    print(f"Fallback to sequential: {FALLBACK_TO_SEQUENTIAL}")
    print("="*60 + "\n")

if __name__ == "__main__":
    print_config()
    
    # Test query detection
    test_queries = [
        "Quiero un hotel en Cancún",
        "Dame tours de buceo y senderismo",
        "Hotel, experiencias y transfer desde el aeropuerto",
        "¿Qué hay que ver en Playa del Carmen?"
    ]
    
    print("\nQuery Detection Tests:")
    print("-"*60)
    for query in test_queries:
        domains = detect_domains(query)
        use_parallel = should_use_parallel(domains)
        print(f"Query: {query}")
        print(f"  Detected domains: {domains}")
        print(f"  Use parallel: {use_parallel}")
        print()
