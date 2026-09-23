# Seconda risposta: torrent, addon, stanze, anonimato e costi

Risposta al documento
[`Cleanvid_analisi_torrent_webapp_desktop.md`](Cleanvid_analisi_torrent_webapp_desktop.md),
più tutto quello che ne è uscito parlandone.

Data: 23 settembre 2026.

Il documento precedente ([`RISPOSTA.md`](RISPOSTA.md)) rispondeva al primo
dossier. Questo risponde al secondo e raccoglie la conversazione che ne è
seguita, comprese le idee di Carlo sulle stanze, sugli addon e sul far pagare
qualcosa.

---

## 1. Il secondo documento è molto migliore del primo

Va detto perché è raro: ha **corretto da solo** il suo punto più debole. Il
primo dossier proponeva un modulo per piattaforma (`sources/youtube.py`,
`sources/twitch.py`); il secondo, al §2, ci ripensa e scrive che il rischio è
«trasformare Cleanvid in un elenco di integrazioni per sito».

Ha anche letto la risposta e ci si è confrontato invece di ripetersi. Su
torrent, web e desktop le conclusioni sono quasi tutte condivisibili.

---

## 2. «Universal Media Discovery»: giusto, ed esiste già

La pipeline `URL → Discovery → Source → Stream → Player` è corretta, e sì —
rispondendo alla sua domanda 2 — il livello `Discovery` prima di `Source`
serve davvero.

Ma è già quello che il progetto fa:

```
/guarda?u=…
   ├── lettore_ufficiale()   tabella di espressioni regolari
   ├── risolvi() → yt-dlp    ~1.800 siti
   └── ripiego sull'embed se l'estrazione fallisce
```

Quindi «Universal Media Discovery» è **il nome giusto per una cosa che c'è**.
Il rischio è trattarlo come un motore da costruire: si finirebbe a scrivere un
instradatore per resolver che non abbiamo. Quello che manca davvero è
l'**uscita unificata** — un descrittore unico al posto di `Lettore` e
`Estratto`. Cioè la cosa già proposta nella prima risposta, e su cui il
documento concorda (§6).

Non c'è un'architettura nuova da costruire: c'è da finire quella che c'è.

---

## 3. Torrent: architettura condivisibile, due fatti pratici mancanti

Il §21 è condivisibile in pieno: sì come backend di streaming, no come
identità, no al catalogo. E il §18 — la distinzione fra «incolli un magnet» e
«cerchi un film» — è la cosa più importante di tutto il documento.

Mancano però due fatti che cambiano la decisione pratica.

### 3.1 WebTorrent nel browser, per un magnet qualunque, non funziona quasi mai

Il documento dice correttamente che «non è equivalente a un client desktop».
La conseguenza però è più dura: un browser raggiunge **solo peer WebRTC**. Per
un magnet preso dallo sciame normale, i peer WebRTC sono tipicamente **zero**.

Funziona quando il contenuto è stato seminato da qualcuno che parla
WebTorrent — l'Internet Archive lo fa, ed è il motivo per cui tutti gli
esempi sulla loro pagina sono quelli.

Una funzione torrent solo-web fallirebbe la maggior parte delle volte. Non
sarebbe una funzione: sarebbe una delusione.

### 3.2 Torrent lato server è una categoria di rischio diversa

Se il motore torrent sta sul nostro server, **noi** entriamo nello sciame: il
nostro indirizzo, la nostra macchina.

Oggi facciamo da proxy a un flusso che l'utente ci ha dato: passiamo dei byte
fra lui e un sito. Entrare in uno sciame vuol dire partecipare a una
distribuzione. Non è la stessa cosa, per nessuno.

### 3.3 Conclusione sul torrent

Il modello lo prevede, noi non lo costruiamo. Se un giorno si costruisce, si
costruisce dove è la macchina dell'utente a entrare nello sciame — cioè nel
desktop.

Costo per tenere la porta aperta oggi: **un campo `tipo` nel descrittore**.
`http | hls | torrent | locale`. Praticamente zero.

---

## 4. Le stanze via torrent: due problemi in un nome solo

Idea di Carlo: fare le stanze e le watchparty via torrent o addon.

Una watchparty sono **due problemi completamente diversi** chiamati con lo
stesso nome:

| | cos'è | quanto pesa | cosa richiede |
|---|---|---|---|
| **sincronia** | «al mio orologio T ero al secondo 42» | byte | ordine, bassa latenza, un padrone |
| **consegna** | i byte del video | gigabyte | banda, tolleranza al ritardo |

**Per la sincronia il torrent è lo strumento sbagliato.** BitTorrent non ha il
concetto di «adesso»: nessun ordinamento, nessuna latenza garantita, una
ricerca sulla DHT sono secondi. Si costruirebbe un sistema di consenso
distribuito per sostituire un WebSocket che funziona e costa niente. E le
stanze anonime su DHT vorrebbero dire un elenco pubblico e non moderabile.

**Per la consegna, invece, l'intuizione è giusta e vale soldi veri.** Dieci
persone in una stanza guardano gli stessi identici segmenti nello stesso
istante; oggi li paghiamo dieci volte.

Quindi: **sincronia con WebSocket, consegna con P2P.**

### 4.1 Gli addon nelle watchparty funzionano peggio, non meglio

Carlo ipotizzava che gli addon potessero servire proprio nelle watchparty.
Tecnicamente è il contrario.

Una watchparty ha bisogno che dieci persone stiano allo stesso secondo dello
stesso flusso. Con un torrent dietro:

- ognuno scarica a velocità diversa e i pezzi arrivano in ordine diverso;
- chi entra in ritardo deve scaricare da capo fino al punto della stanza;
- saltare avanti costa, perché quei pezzi magari non li ha nessuno vicino;
- non esiste il «bordo della diretta», che è quello che tiene insieme la
  stanza.

Un flusso HLS è **già sincrono per costruzione**: tutti chiedono il segmento
N nello stesso momento. Un torrent è **asincrono per costruzione** — è fatto
apposta per prendere i pezzi in disordine.

L'unico modo per farlo funzionare è che il server scarichi il torrent e serva
HTTP a tutti: e allora nello sciame c'è il server, cioè il punto 3.2.

---

## 5. «Chi apre la stanza ospita»: i numeri

Seconda idea di Carlo: chi crea la stanza anonima ne diventa l'ospite
effettivo, e la piattaforma è solo il punto d'incontro.

L'intuizione sulla banda è giusta. I numeri della versione «a stella» no.

**La banda in salita.** Una connessione di casa è asimmetrica. FTTC tipica:
100 giù / **20 su**. Un 1080p sono ~5 Mbps.

```
20 Mbps in salita − margine ≈ 15 utilizzabili
15 ÷ 5 = 3 partecipanti
```

Chi apre la stanza ne regge **tre**. Con fibra vera (300 in salita) venti, ma
non ci si può costruire sopra: dipende dalla linea di chi apre, e non la
conosciamo.

**Il CGNAT.** Una fetta consistente delle connessioni di casa sta dietro NAT
condiviso: due peer non si trovano da soli e serve un relè. Il relè saremmo
noi, e lì la banda la ripaghiamo comunque, senza poter prevedere quante volte.

**La scheda chiusa.** Chi apre esce e la stanza muore, a meno di rinegoziare
tutto con un altro.

### 5.1 La versione che regge: a rete, non a stella

```
       a stella                        a rete

        chi apre                    noi (origine)
       ╱   │   ╲                        │
      A    B    C                       A
                                      ╱   ╲
   3 persone al massimo                B     C
   e se lui esce, finita             ╱ ╲   ╱ ╲
                                    D   E F   G

                               ognuno ridà quello che ha gia'
                               l'origine spinge 1-2 copie, non 10
```

Chi ha appena scaricato il segmento 412 lo passa a chi sta per chiederlo.
Nessuno deve reggere tutti, e se qualcuno esce la rete si richiude da sola.

È `p2p-media-loader`, si innesta in hls.js — la libreria già in uso — ed è
open source. È la tecnologia con cui si distribuiscono i grandi eventi in
diretta.

### 5.2 La responsabilità non si sposta

Carlo ha chiarito che non intendeva spostare la responsabilità di nascosto, e
la precisazione è accolta. Resta però un fatto tecnico che vale la pena
lasciare scritto, perché è controintuitivo:

**anche con l'ospite che ospita, noi restiamo l'elenco delle stanze e il punto
d'incontro.** Senza di noi nessuno trova la stanza e nessuno si collega. Chi
offre il luogo d'incontro e fa incontrare le persone non è in posizione
neutra.

Quello che si sposta davvero è la **banda**, non la responsabilità.

---

## 6. Anonimato e P2P sono incompatibili

Questa è la scoperta più utile di tutta la conversazione, ed è venuta fuori
solo precisando cosa si intende per «anonimo».

Carlo vuole che **in una stanza nessuno sappia chi sono gli altri.**

Perché due browser si scambino byte direttamente devono conoscersi
l'indirizzo IP: WebRTC lo scambia all'inizio — si chiamano *ICE candidates* —
e non è aggirabile, perché senza non esiste collegamento diretto.

L'unico modo di avere P2P senza mostrare gli indirizzi è far passare tutto da
un relè. Ma il relè saremmo noi, e a quel punto paghiamo **ogni byte due
volte**: in entrata e in uscita. Il risparmio non sparisce soltanto — diventa
un costo maggiore di adesso.

Quindi è un bivio pulito:

| | chi vede cosa | chi paga la banda |
|---|---|---|
| **stanza anonima** | nessuno vede niente di nessuno | **noi, tutta** |
| **stanza con P2P** | i partecipanti si vedono l'IP | noi ~20%, il resto fra loro |

Una via di mezzo esiste: **P2P spento di serie**, accendibile da chi vuole,
con scritto chiaro cosa comporta. Ma non può essere il funzionamento normale
di una stanza anonima.

**Una precisazione che serve:** l'anonimato desiderato c'è già. «Lontra 417»
non dice niente di nessuno, e fra i partecipanti nessuno sa chi è l'altro.
Quello che WebRTC romperebbe non è l'identità, è l'anonimato **di rete**. Sono
due cose diverse, e la prima è già risolta dal passo 1.

---

## 7. Addon e catalogo: dove sta la linea

Carlo non esclude gli addon, anche per arrivare a un catalogo di film.

**Tecnicamente è fattibile, e facile.** Il protocollo addon di Stremio è un
servizio HTTP che risponde JSON su quattro risorse; un client si scrive in due
giorni, molto meno del muro.

Ma la domanda vera non è se si può fare.

### 7.1 Cosa cambia

Oggi cleanvid ha una proprietà precisa: **l'utente porta il link**. Ce l'ha
già, noi lo apriamo pulito, il rapporto con il contenuto è suo.

Con un catalogo quella proprietà sparisce. Non è più «apro quello che mi dai»,
è «ti offro cosa guardare». Non è una funzione in più: è un altro prodotto.

### 7.2 Perché la protezione di Stremio non si trasferisce

Stremio spedisce **un'applicazione vuota**. Gira sul computer di chi la
installa, con il suo indirizzo, e gli addon sono di terzi. La distanza che li
protegge è quella: distribuiscono software, non un servizio.

`cleanvid-platform` **non è un'applicazione: è un servizio ospitato.** Con un
catalogo dentro, la posizione non è quella di Stremio — è quella di chi
gestisce il servizio. Con il proprio server, il proprio indirizzo, il proprio
nome sul dominio, e utenti anonimi senza traccia.

Combinato con stanze anonime e condivisione P2P dei segmenti diventa: persone
senza identità che si scambiano fra loro pezzi di contenuti presi da un
catalogo, attraverso infrastruttura scritta e gestita da una persona sola.

In Italia il quadro su questo è particolarmente severo. Questo documento non
è un parere legale e non vuole esserlo: dice solo che **in quello scenario il
rischio è personale**, e che prima di pubblicare qualcosa del genere vale la
pena parlarne con qualcuno che di mestiere faccia l'avvocato.

### 7.3 Le tre versioni

| | cos'è | dove sta il rischio |
|---|---|---|
| **A** | client addon, l'utente incolla l'indirizzo del *suo* addon, noi non ne distribuiamo e non ne facciamo cercare | attenuato, ma si resta l'operatore |
| **B** | gli addon stanno **nel desktop**, non nel servizio web | sul computer di chi lo usa — la posizione di Stremio, davvero |
| **C** | servizio web con catalogo e stanze anonime | tutto sull'operatore |

**B è la risposta, e non è un compromesso al ribasso.**

### 7.4 La stessa linea di faglia, per la quarta volta

Modalità ascolto, file locali, torrent nativo, addon: sono **le stesse quattro
cose** che finiscono sempre dalla stessa parte.

Non è un caso. Sono tutte cose in cui **chi usa deve essere anche chi espone
sé stesso**. Su un servizio ospitato da altri, quella condizione non si può
soddisfare.

---

## 8. Web e desktop: esistono già

Il §20 propone due front-end che condividono il core. È la cosa che **già
esiste**, con altri nomi:

| il documento dice | da noi si chiama |
|---|---|
| Desktop App — browser/CDP, file locali, torrent nativo | `~/cleanvid`, il file unico |
| Web App — stanze, chat, account, player universale | `~/cleanvid-platform` |

E le tre cose che il documento mette nel desktop sono **esattamente le tre**
che avevamo deciso non possono stare su un servizio pubblico. Stessa linea di
faglia, vista da due lati.

Non condivisibile invece il §14 letto alla lettera, «un core condiviso fra i
due». Condividere codice fra un processo locale in Python e un servizio
multi-utente costa molto e rende poco: i due condividono i **concetti**
(Media, Stream, biblioteca), non il codice. Il codice condiviso fra due
programmi che girano in mondi diversi diventa il posto dove nessuno dei due
può cambiare niente.

---

## 9. Quanto costa, e cosa si può far pagare

Carlo ha detto che vuole far pagare qualcosa ma non sa ancora cosa, perché non
sa come verrà fuori. È la risposta giusta a questo punto del progetto. Quello
che si può già dire è **cosa costa**, perché è misurato.

Il costo è quasi tutto uno: **la banda.**

```
1080p ≈ 5 Mbps  →  2,25 GB all'ora, per ogni persona
stanza da 10, due ore  →  45 GB
```

Tutto il resto è rumore:

- l'estrazione sono ~5 secondi di CPU, **in cache condivisa** per
  `(url, qualità)`: una estrazione, dieci spettatori;
- le copertine sono kilobyte e stanno su disco;
- Postgres e Redis a questa scala non se ne accorgono.

E il conto cambia di **dieci volte** a seconda di dove si ospita:

| | banda | una stanza da 10, 2 ore |
|---|---|---|
| fornitore europeo (tipo Hetzner) | 20 TB inclusi ≈ **8.900 ore-spettatore**, poi ~1 €/TB | ~0,05 € |
| hyperscaler | ~0,09 $/GB | **~4 €** |

**La scelta dell'hosting decide il modello di business più della lista delle
funzioni.**

### 9.1 Le due leve

Sul costo si agisce solo in due modi:

1. **il P2P** — taglia fino all'80% della banda, ma costa l'anonimato di rete
   (§6);
2. **la qualità** — 480p costa un quinto di 1080p.

Sono anche le due candidate naturali a distinguere gratis da pagato, senza
dover inventare niente.

### 9.2 Su cosa paga la gente

Non per «niente pubblicità»: quello lo fa un'estensione, gratis. Paga per le
cose che **richiedono un server**: le stanze, ritrovare la propria roba su
tutti i dispositivi, che il servizio ci sia quando serve.

Cioè esattamente quello che stiamo costruendo.

### 9.3 Una cosa da sapere

**Far pagare cambia anche la posizione legale.** Un servizio a pagamento che
apre contenuti di terzi viene guardato diversamente da uno strumento gratuito.
Non è un motivo per non farlo: è un motivo per avere le idee chiare su cosa si
vende prima di venderlo.

---

## 10. Decisioni prese

1. **Descrittore unico** al posto di `Lettore` ed `Estratto`, con un campo
   `tipo` che prevede `http | hls | torrent | locale | addon`. Mezza giornata,
   toglie 36 ramificazioni fra modelli e rotte, e tiene aperte tutte le porte
   gratis.
2. **Sottotitoli**: mancano del tutto, yt-dlp li dà già.
3. **Testo legale, pagina «cos'è», contatto per le segnalazioni**, prima di
   pubblicare. Compresa la riga in fondo alla pagina, che oggi dice «Gira sul
   tuo computer» e il giorno della pubblicazione diventa falsa.
4. **Sincronia delle stanze con WebSocket**, non con DHT o torrent.
5. **Addon e torrent, se mai, nel desktop** — non nel servizio web.
6. **Niente catalogo sul servizio web.**

---

## 11. Decisioni lasciate aperte, e quando si prendono

| cosa | quando decidere | da cosa dipende |
|---|---|---|
| P2P nelle stanze | **progettando le stanze**, non dopo | decide il token: deve essere per stanza, non per utente |
| anonimato di rete o P2P | insieme al punto sopra | sono alternativi (§6) |
| cosa far pagare | quando le stanze saranno usate | serve vedere cosa la gente usa davvero |
| dove ospitare | prima di pubblicare | decide il modello di business (§9) |
| addon nel desktop | quando il desktop tornerà in vita | non c'è fretta |

Due cose che **vanno sapute prima** di scrivere le stanze, altrimenti sono
due settimane invece di due righe:

- il token dei segmenti dovrà essere **per stanza**, o due partecipanti non
  potranno scambiarsi lo stesso pezzo;
- la condivisione P2P dev'essere **spegnibile**, e il fatto che mostri
  l'indirizzo IP va detto a chi la accende.

---

## 12. Cosa non faremo

Un catalogo pensato per trovare copie non autorizzate non lo costruiamo. Il
client del protocollo addon in sé è neutro — esistono addon legittimi, e
l'Internet Archive ne è pieno; la differenza sta in cosa ci si mette dentro e
chi lo ospita.

---

## 13. E intanto

Tutto questo è progettazione. La cosa che il progetto aspetta davvero è ancora
la stessa dei due documenti precedenti: **registrazione** (passo 4) e
**stanze** (passi 5-7).

Sono il motivo per cui `cleanvid-platform` esiste invece di essere una
ripulita del file unico, e non c'è ancora una riga. Ogni decisione di questo
documento diventa più facile dopo averle viste funzionare, e nessuna di esse
le blocca.
