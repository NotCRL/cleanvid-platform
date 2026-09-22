.PHONY: su giu avvia prova stile tipi

su:      ## database e redis
	docker compose up -d
giu:
	docker compose down
avvia:   ## il server, che si ricarica da solo
	uvicorn cleanvid.main:app --reload --app-dir src
prova:   ## i test, su un database a parte che viene creato se non c'e'
	@docker compose exec -T db psql -U cleanvid -d postgres -tAc \
		"SELECT 1 FROM pg_database WHERE datname='cleanvid_test'" | grep -q 1 || \
		docker compose exec -T db createdb -U cleanvid cleanvid_test
	pytest -q
stile:
	ruff check src tests && ruff format --check src tests
tipi:
	mypy src
