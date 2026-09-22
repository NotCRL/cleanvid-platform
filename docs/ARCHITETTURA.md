# cleanvid — architettura

## Perché un progetto nuovo e non un rifacimento

Il cleanvid che gira oggi è un buon prodotto e una **cattiva base** per quello
che vuoi diventare. Non per come è scritto: per quello che dà per scontato.
Quattro assunzioni, tutte invertite rispetto a un servizio online:

| Oggi | Serve |
|---|---|
| `HISTORY`, `FAVS`, `SOURCES`, `GRUPPI` sono liste globali in memoria | dati per persona |
| si salva riscrivendo un file JSON intero, senza blocchi | scritture concorrenti |
| `ThreadingHTTPServer`: un thread per connessione | connessioni lunghe (stanze) a migliaia |
| un `yt-dlp` per ogni apertura, ~5 s di CPU | una estrazione condivisa da tutti quelli che guardano la stessa cosa |

Le prime due non si aggiustano: *sono* il modello dei dati. La terza è il
motivo per cui la watchparty non si può innestare — una stanza è fatta di
connessioni che restano aperte, e un thread ciascuna finisce a poche centinaia.

**Quello che si porta dietro, e vale più del resto:** la logica video. La
strategia di estrazione, il manifest HLS costruito a mano, i segmenti
pubblicitari riconosciuti e saltati, il player a due tracce, la tabella degli
errori tradotti in italiano leggibile. Sono anni-uomo di dettagli trovati
sbattendoci la testa, e si trasportano quasi intatti in `media/`.

## La forma

```
src/cleanvid/
  config.py        tutto da variabili d'ambiente, nessun default pericoloso
  main.py          solo montaggio, zero logica
  models/          le tabelle: qui si decide cosa sarà possibile
  api/             le rotte HTTP
  rooms/           stanze: hub, protocollo WebSocket
  media/           ← il valore portato dal cleanvid di oggi
    extract.py     yt-dlp: risoluzione, qualità, coppia video+audio
    hls.py         manifest costruiti a mano, pubblicità saltata
    proxy.py       i byte, con Range
    diagnose.py    errori in italiano
    cache.py       Redis: un'estrazione vale per tutti
  web/             pagine e statici
```

## Le tre decisioni che non si possono rimandare

### 1. Anonimo e registrato sono la stessa riga

Chi arriva senza fare niente riceve un utente vero con un id vero. Registrarsi
**attacca credenziali a quella riga**, non ne crea una nuova. Chi si iscrive
non perde niente — ed è esattamente il momento in cui la gente abbandona.

L'alternativa (anonimi nel browser, registrati nel database) è più semplice il
primo giorno e impossibile il giorno delle stanze: una stanza ha un proprietario
e degli ospiti, e «un oggetto nel localStorage di qualcuno» non è un
proprietario.

### 2. `utente_id` su ogni riga, da subito

Anche adesso che l'utente è uno solo. Aggiungerlo dopo significa migrare dati
già in produzione e rileggere ogni query: è il tipo di lavoro che si rimanda
per sempre.

### 3. Il polso della riproduzione non tocca il disco

Una stanza da dieci persone manda posizione e stato molte volte al minuto. In
Postgres, quel traffico diventa il collo di bottiglia della festa. Su disco va
solo ciò che deve sopravvivere a un riavvio: proprietario, membri, chat. La
posizione vive in Redis, dove nasce e muore con la stanza.

## Come si tengono sincroni dieci schermi

Nessuno insegue nessuno. Chi comanda non manda «vai al secondo 42»: manda
**«al mio orologio T io ero al 42 e stavo andando»**. Ogni ospite calcola da
solo dove dovrebbe essere e ci arriva.

È lo stesso problema del player a due tracce, già risolto: se lo scarto è
piccolo si cambia impercettibilmente la velocità finché rientra, e si salta
solo quando un salto si sente meno di uno sfasamento. Un sistema che salta a
ogni messaggio singhiozza, e chi guarda in compagnia nota il singhiozzo molto
più di mezzo secondo di ritardo.

Le soglie stanno tutte in `rooms/protocol.py`, in fondo, in un posto solo: si
regolano con gli occhi su uno schermo vero, non a tavolino.

## Una estrazione, tutti quelli che guardano

`yt-dlp` è la cosa più cara che facciamo: ~5 secondi di CPU. La chiave della
cache è `(url, qualità)` e **non** l'utente — dieci persone nella stessa stanza
costano una estrazione sola. Il TTL è corto perché gli indirizzi dei flussi
scadono, e un semaforo limita quante ne girano insieme: senza, un picco di
aperture mette in ginocchio la macchina.

## I passi

1. **Fondamenta** — `models/`, migrazioni, utente anonimo col cookie firmato,
   una pagina che apre un video. Nessuna funzione nuova: si dimostra solo che
   la biblioteca per-utente regge. **Fatto il 22/09/2026**; com'è andata, e i
   due bug che ci sono voluti, in [`REGISTRO.md`](REGISTRO.md).
2. **Trasloco di `media/`** — la logica video si sposta dal file unico. Qui
   servono i test: è il pezzo che non deve peggiorare. **Fatto il
   22/09/2026**: estrazione, manifest HLS, proxy dei byte, rimozione della
   pubblicità cucita nel flusso. Il muxing in diretta non è passato, e il
   perché sta in [`REGISTRO.md`](REGISTRO.md).
3. **Biblioteca** — cronologia, preferiti, fonti, gruppi, continua a guardare,
   per persona. A questo punto il servizio è pubblicabile.

   *Fuori ordine, fatto il 22/09/2026:* il sito in quattordici lingue e la
   struttura SEO — una lingua per indirizzo, hreflang, mappa del sito, pagine
   dei video fuori dall'indice. Anticipato perché sono decisioni di struttura:
   spostare gli indirizzi dopo la pubblicazione costa i posizionamenti già
   guadagnati. Vedi [`LINGUE-E-SEO.md`](LINGUE-E-SEO.md).
   *Fatto il 22/09/2026 anche il muro* (da 1 a 4 video insieme, gruppi
   salvati), portato dal file unico con i suoi vincoli. Vedi
   [`REGISTRO.md`](REGISTRO.md).

4. **Registrazione** — email e password attaccate alla riga che c'è già.
5. **Stanze, prima versione** — crei, condividi il link, si guarda insieme.
   Niente elenco, niente password: solo la sincronia, che è la parte difficile.
6. **Chat**, che è facile una volta che il WebSocket c'è.
7. **Ricerca delle stanze** — visibilità, password, elenco di quelle aperte.

Ogni passo è pubblicabile da solo. Nessuno richiede di rifare quello prima.

## Cosa non passa di qui

**La modalità ascolto non sopravvive al multi-utente.** Apre un Chromium vero
sulla macchina che ospita e lo lascia guidare da chi sta dall'altra parte: in
casa è una comodità, su un servizio pubblico è dare il proprio browser a
chiunque. Nel cleanvid di oggi l'ho già spenta sotto `--public`. Se serve
online va ripensata da zero: un browser usa e getta, in un contenitore isolato,
senza profilo e senza rete verso l'interno. È un progetto a sé, e caro.
