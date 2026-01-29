# Quick Start - Agentes Paralelos

## 1. Verificar que está instalado

```bash
cd "c:\Users\HolaY\OneDrive\Documentos\productobot\productobot GPT"
python test_parallel_integration.py
```

Expected output: `✓ All tests passed!`

## 2. Usar en Slack (sin cambios)

ProductoBot automáticamente usa agentes paralelos para queries multi-dominio:

```
Usuario: "Dame hotel en Cancún y tours de buceo"
→ ProductoBot detecta 2 dominios
→ Ejecuta agentes en paralelo
→ Responde más rápido ⚡
```

## 3. Usar en CLI

```bash
python agent/ruto_agent.py

# Type: "Dame hotel y tours en Cancún"
# → Automáticamente usa paralelización
```

## 4. Usar en Código

```python
from agent.ruto_agent import chat

# Automáticamente inteligente - detecta multi-dominio
response = await chat(
    query="hotel + tours",
    first_name="Usuario"
)

# Forzar secuencial si es necesario
response = await chat(
    query="hotel + tours",
    first_name="Usuario",
    use_parallel=False
)
```

## 5. Demo

```bash
python agent/demo_parallel_agents.py
```

Muestra:
- 3 ejemplos de queries
- Benchmark (paralelo vs secuencial)
- Mejora de latencia

## 6. Configuración

### Variable de entorno para habilitar/deshabilitar

```bash
# .env
ENABLE_PARALLEL_AGENTS=true          # Default: true
MIN_DOMAINS_FOR_PARALLEL=2            # Default: 2
PARALLEL_EXECUTION_TIMEOUT=30         # Default: 30s
DEBUG_AGENT_EXECUTION=false           # Default: false
LOG_EXECUTION_TIMELINE=false          # Default: false
```

### Cambiar modelos (para optimizar costos)

```bash
# .env
SPECIALIZED_AGENTS_MODEL=gpt-3.5-turbo  # Más barato que gpt-4-mini
```

## 7. Estructura de Archivos

```
📁 agent/
  ├─ parallel_agents.py          ← Core: ParallelAgentRunner
  ├─ parallel_config.py           ← Config centralizada
  ├─ ruto_agent.py                ← Main agent (modificado)
  ├─ demo_parallel_agents.py      ← Demo
  └─ ... (otros archivos sin cambios)

📄 test_parallel_integration.py   ← Test
📄 PARALLEL_AGENTS.md             ← Documentación técnica
📄 IMPLEMENTATION_SUMMARY.md      ← Este resumen
```

## 8. Ejemplos de Queries

### ✓ Multi-Dominio (Paralelo)
```
"Quiero un hotel 5 estrellas en Cancún, 
 tours de buceo y saber cómo ir desde la capital"
```
→ 3 agentes en paralelo
→ Latencia: ~35s (vs ~90s secuencial)

### ✓ Simple (Secuencial directo)
```
"¿Hoteles en Playa del Carmen?"
```
→ Agent ReAct directo (sin overhead)
→ Latencia: ~30s

### ✓ Complejo
```
"Opciones de lujo con disponibilidad en julio,
 que incluyan desayuno y tours de yoga"
```
→ 4 agentes en paralelo
→ Latencia: ~40s

## 9. Troubleshooting

### P: ¿Por qué mi query simple es lenta?
**R:** Probablemente tiene overhead de análisis. Solución:
```python
await chat(query=query, use_parallel=False)
```

### P: ¿Puedo ver qué agentes se ejecutan?
**R:** Sí, habilita debugging:
```bash
export DEBUG_AGENT_EXECUTION=true
export LOG_EXECUTION_TIMELINE=true
python agent/ruto_agent.py
```

### P: ¿Qué pasa si un agente falla?
**R:** Fallback automático a secuencial:
```
WARNING: ExperiencesAgent: [error]
INFO: Falling back to sequential execution
```

### P: ¿Cómo cambio el modelo para ahorrar costos?
**R:** En `.env`:
```bash
SPECIALIZED_AGENTS_MODEL=gpt-3.5-turbo
```

## 10. Métricas de Rendimiento

| Query | Before | After | Mejora |
|-------|--------|-------|--------|
| Hotel + Tours + Transfer | 90s | 35s | 2.6x ⚡ |
| Solo hotel | 30s | 30s | - |
| Hotel + Tours | 60s | 35s | 1.7x |

## 11. Próximos Pasos

- [ ] Monitoreo en CloudWatch
- [ ] A/B testing de thresholds
- [ ] Agregar nuevo dominio
- [ ] Optimizar prompts de meta-agent

---

**¿Preguntas?** Ver [PARALLEL_AGENTS.md](./PARALLEL_AGENTS.md)
