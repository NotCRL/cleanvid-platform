# Lingue e motori di ricerca

Due cose che sembrano separate e sono la stessa. Un sito in quattordici lingue
che non si fa trovare in quattordici lingue ha fatto metà del lavoro e pagato
tutto il prezzo.

---

## Parte funzionale — cosa vede una persona

**Ogni lingua ha il suo indirizzo.** `/it/`, `/en/`, `/ja/`. Un link mandato a
qualcuno arriva nella lingua in cui è stato copiato, non in quella del
destinatario: chi condivide una pagina sa cosa sta condividendo.

**Chi arriva sulla radice viene mandato nella lingua giusta.** L'ordine è:
quello che ha scelto, poi quello che dice il suo browser, poi l'inglese.

**Il cambio lingua sta nelle impostazioni**, raggiungibili dall'ingranaggio in
alto a destra — che mostra anche la lingua attuale (`⚙ IT`), così si capisce
dov'è senza doverci entrare. La scelta si salva in due posti: sulla riga
dell'utente, perché lo segua ovunque abbia il suo cookie, e in un cookie a
parte, perché chi apre la radice venga mandato subito senza aspettare il
database. In fondo a ogni pagina c'è anche l'elenco completo delle lingue, come
link veri.

**Se il browser chiede un'altra lingua, si propone.** Una riga in cima, con un
link. Non un rimbalzo: chi ha aperto un link in italiano voleva l'italiano, e
portarlo altrove significherebbe rompere ogni link condiviso.

**Le quattordici lingue.** Inglese, italiano, spagnolo, portoghese, francese,
tedesco, polacco, turco, russo, arabo (scritto da destra a sinistra), hindi,
indonesiano, giapponese, cinese.

---

## Parte tecnica — come è fatto

### I moduli

| Dove | Cosa |
|---|---|
| `lingue/catalogo.py` | l'elenco delle lingue e la lettura di `Accept-Language` |
| `lingue/__init__.py` | il caricamento dei testi e la funzione `t()` |
| `lingue/testi/*.json` | un file per lingua, 68 frasi ciascuno |
| `api/contesto.py` | quello che ogni pagina sa di sé: lingua, indirizzi, testi |
| `seo.py` | canonical, hreflang, robots, sitemap, dati strutturati |
| `strumenti/traduci.py` | la traduzione con Claude, fuori dal servizio |

### Le cinque decisioni

**1. La lingua sta nell'indirizzo, non in un cookie.** Un motore di ricerca
indicizza indirizzi, non sessioni. Se la stessa pagina cambiasse lingua in base
a un cookie, di quattordici versioni ne esisterebbe una sola per chi cerca —
quella che al crawler è capitata.

**2. Non si reindirizza in base al paese.** È la cosa che sembra più gentile e
fa più danno. Google visita il sito quasi sempre da indirizzi americani: con un
rimbalzo su IP vedrebbe per sempre la sola versione inglese, e le altre tredici
non entrerebbero mai nell'indice. In più chi vive all'estero, o usa una VPN, si
ritrova inchiodato a una lingua che non ha scelto.

`Accept-Language` dice **che lingua parla una persona**; l'indirizzo IP dice
**dov'è il suo router**. Sono due domande diverse, e per questa serve la prima.
Un italiano a Berlino ha ancora `it` in cima e un IP tedesco.

**3. Le hreflang si generano da una funzione sola.** Devono essere reciproche:
se la pagina italiana dichiara quella spagnola, quella spagnola deve dichiarare
l'italiana. Google butta via in blocco i gruppi che non tornano, senza dirlo.
Scriverle a mano in quattordici modelli è la garanzia che prima o poi una resti
indietro, quindi si generano tutte insieme, sempre, in `seo.py`. C'è anche
`x-default`, per chi non rientra in nessuna: è l'inglese.

**4. Le pagine dei video non si indicizzano.** `guarda?u=...` è uno spazio di
indirizzi infinito: ogni link che qualcuno incolla è una pagina nuova, tutte
uguali tranne un iframe, e il contenuto dentro è di qualcun altro. Un motore
che ci trova dentro un milione di pagine sottili e duplicate non ci premia: ci
classifica come sito di scarto, e si porta dietro anche la home. Quindi
`noindex` sulla pagina e `Disallow` in `robots.txt`.

Si indicizza quello che abbiamo scritto noi: la home, la spiegazione di come
funziona, le domande frequenti. È anche il motivo per cui quelle sezioni
esistono — senza, la home sarebbe un campo di testo e non ci sarebbe niente per
cui trovarci.

`/flusso/` e `/segmento` sono chiusi per un'altra ragione: sono byte di video,
e farli scaricare a un robot è banda buttata. La nostra, e con questi volumi si
sente.

**5. `/it` e `/it/` sono due indirizzi.** La mappa del sito e il `canonical`
devono dichiarare lo stesso, o ci si contraddice da soli su ogni pagina. È già
successo una volta: vedi il registro.

### Il resto, che si paga se manca

- `<html lang>` corretto, e `dir=rtl` per l'arabo.
- Titolo e descrizione diversi per lingua, sotto i limiti in cui Google taglia.
- `og:` e `twitter:card` per chi condivide il link in una chat.
- Dati strutturati `FAQPage`: sono le domande che diventano il riquadro nei
  risultati. Prese dallo stesso catalogo della pagina — dichiarare qualcosa che
  sulla pagina non c'è fa togliere il riquadro, e a volte di peggio. Un test
  verifica che ogni domanda dichiarata compaia davvero nell'HTML.
- Mappa del sito con le hreflang dentro: per un sito nuovo è la strada più
  veloce perché tutte e quattordici le versioni vengano scoperte insieme.

---

## La traduzione con Claude

```bash
python strumenti/traduci.py --controlla   # cosa manca, senza chiamare niente
python strumenti/traduci.py               # traduce ciò che manca
python strumenti/traduci.py es fr         # solo queste
python strumenti/traduci.py --tutto       # rifà tutto da capo
```

Serve `ANTHROPIC_API_KEY`.

**Si traduce prima, non mentre qualcuno guarda la pagina.** Tre motivi, in
ordine di gravità:

1. *I motori di ricerca.* Un testo che cambia a ogni visita è un testo di cui
   Google non sa cosa indicizzare. Una traduzione stabile è una pagina vera;
   una generata al volo è una pagina che oggi dice una cosa e domani un'altra.
2. *Nessuno la rilegge.* Una traduzione automatica messa online senza che
   qualcuno l'abbia guardata è, testualmente, ciò che Google considera
   contenuto di scarto. Qui il risultato finisce in un file, entra in un
   commit, e si può correggere a mano — e la correzione resta.
3. *Il costo e il tempo.* Una chiamata a un modello per pagina significa pagare
   ogni visita e far aspettare un secondo prima di mostrare qualcosa.

**Le impronte.** In `testi/.impronte.json` c'è, per ogni lingua e ogni chiave,
l'impronta della frase italiana da cui la traduzione è nata. Quando una frase
italiana cambia, lo strumento sa quali traduzioni sono invecchiate. Senza,
l'unico modo sarebbe ritradurre tutto ogni volta — o non accorgersene mai. Le
correzioni fatte a mano restano: si ritraduce solo ciò che è cambiato davvero.

**Il controllo dei segnaposto.** `{titolo}`, `{piattaforma}`, `{lingua}` devono
sopravvivere alla traduzione identici. Se un modello ne sposta o rinomina uno,
la pagina mostra testo rotto. Lo strumento lo verifica e lo segnala; un test lo
verifica di nuovo su tutti i cataloghi, perché una correzione a mano può
romperlo esattamente allo stesso modo.

**L'italiano è l'originale**, perché è la lingua in cui il progetto viene
pensato. L'inglese è scritto a mano anche lui: è la versione che vedrà più
gente di tutte, e non merita di essere una traduzione automatica.
