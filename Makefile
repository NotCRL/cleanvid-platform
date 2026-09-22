.PHONY: su giu avvia prova stile tipi

su:      ## database e redis
	docker compose up -d
giu:
	docker compose down
avvia:   ## il server, che si ricarica da solo
	uvicorn cleanvid.main:app --reload --app-dir src
prova:
	pytest -q
stile:
	ruff check src tests && ruff format --check src tests
tipi:
	mypy src
