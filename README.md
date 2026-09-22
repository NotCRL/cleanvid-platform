# cleanvid

Incolli il link di una pagina e resta il video.

Questo è il progetto **servizio**: multi-utente, pubblicabile, pensato per
crescere fino alle stanze condivise. Il cleanvid a file unico che gira in
locale resta in `~/cleanvid` e fa da riferimento: la sua logica video si
trasferisce qui in `media/`, il resto no — e il perché sta in
[`docs/ARCHITETTURA.md`](docs/ARCHITETTURA.md).

## Avvio

```bash
cp .env.example .env
python3 -c "import secrets;print('CLEANVID_SEGRETO='+secrets.token_urlsafe(48))" >> .env
make su          # postgres e redis
pip install -e ".[dev]"
alembic upgrade head
make avvia       # http://localhost:8000
```

## Dove sta cosa

| Cartella | Cosa c'è |
|---|---|
| `models/` | le tabelle. **Qui si decide cosa sarà possibile** |
| `media/` | estrazione, manifest HLS, proxy dei byte, diagnosi |
| `rooms/` | stanze: protocollo WebSocket e hub |
| `api/` | le rotte |
| `web/` | pagine e statici |

## Le tre decisioni da non rimandare

1. **Anonimo e registrato sono la stessa riga.** Registrarsi attacca
   credenziali a un utente che esiste già: nessuno perde niente iscrivendosi.
2. **`utente_id` su ogni riga da subito**, anche finché l'utente è uno solo.
3. **Il polso della riproduzione non tocca il disco.** Postgres per ciò che
   deve sopravvivere a un riavvio, Redis per ciò che vive con la stanza.

Per esteso, con le ragioni: [`docs/ARCHITETTURA.md`](docs/ARCHITETTURA.md).
