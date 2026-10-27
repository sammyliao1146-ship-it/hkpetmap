from backend.app.config.factory import create_app
from backend.app.routers import assistant, pets, parking, plans

app = create_app([pets.router, assistant.router, parking.router, plans.router])
