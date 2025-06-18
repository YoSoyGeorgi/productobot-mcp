def build_home_tab_view(user_name):
    """
    Build the home tab view for the Slack app
    
    Args:
        user_name: The name of the user to personalize the welcome message
        
    Returns:
        dict: The view configuration for the home tab
    """
    return {
        "type": "home",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Bienvenido a ProductoBot, {user_name} 👋",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*ProductoBot* es tu asistente virtual para Rutopia. Te ayudo a encontrar experiencias, alojamientos y transporte para tus clientes."
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*¿Cómo usarme?* 🤔"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "• *Mencióname* en cualquier canal con `@ProductoBot`\n• *Envíame mensajes directos*\n• *Sé específico* con lo que buscas"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*¿Qué puedo hacer por ti?* ✨"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🎯 *Experiencias:* \"Busco experiencias de aventura en Oaxaca para 4 personas\"\n🏨 *Alojamientos:* \"Necesito hoteles económicos en Tulum para parejas\"\n🚗 *Transporte:* \"Transporte de CDMX a Cuernavaca para 6 personas\""
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Consejos para mejores resultados:* 💡"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "• Incluye el *destino* o ubicación\n• Menciona *cuántas personas* van\n• Especifica si buscas algo *económico* o con características específicas\n• Pregunta por *códigos de producto* si necesitas hacer una cotización"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_¡Estoy aquí para hacer tu trabajo más fácil!_ 🚀"
                }
            }
        ]
    } 