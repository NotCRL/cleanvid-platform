# Come lavoriamo

Regole concordate il 22/09/2026. Non sono principi generali: ognuna nasce da
qualcosa che è andato storto, e il caso è citato perché si capisca il costo.

## 1. Una modifica per volta

Si cambia una cosa, si verifica, poi la successiva.

*Il caso:* quando la cattura dei flussi smise di funzionare, erano state
cambiate cinque cose insieme — componente per i contenuti protetti, versione
dichiarata del browser, maschere anti-rilevamento, modalità compatibilità,
filtri di rete. Nessuno dei due poteva dire quale avesse rotto cosa, e servì
costruire una modalità "come prima" solo per tornare indietro a tentoni.

## 2. Mai ripieghi silenziosi

Se il programma non può fare ciò che ha promesso, lo dichiara a schermo. Un
ripiego che non si vede è peggio di un errore visibile.

*Il caso:* quando il profilo con le estensioni era occupato, la modalità
ascolto ne apriva uno vuoto **senza dirlo**. Si navigava senza blocco
pubblicità e non c'era modo di accorgersene.

## 3. Dire sempre cosa è stato verificato, e cosa no

Le prove su pagine costruite apposta servono a non rompere ciò che funziona.
La conferma che una cosa funziona arriva solo dalla prova sul caso vero.

*Il caso:* le pagine di prova passavano mentre i siti reali fallivano. Dire
"verificato" senza dire *su cosa* fa perdere tempo a entrambi.

## 4. Le decisioni si scrivono in un file

Ogni scelta non ovvia va nella documentazione col suo perché, non solo in chat.

*Il caso:* una sessione intera di lavoro — più di tremila righe — è rimasta nel
codice mentre il ragionamento che l'aveva guidata è andato perso. Il file
resta, la conversazione no.

Dove va cosa:

| Documento | Contenuto |
|---|---|
| `ARCHITETTURA.md` | le scelte strutturali e le loro ragioni |
| `FUNZIONALITA.md` | cosa fa il prodotto, per chi lo usa |
| `TECNICA.md` | come è fatto dentro |
| `REGISTRO.md` | una voce per ogni intervento |

## 5. Documentare ogni intervento

Funzione nuova, bug corretto o scelta tecnica: una voce in `REGISTRO.md` con
cosa cambia per chi usa, come è fatto, perché così, cosa è stato verificato.
**Nulla entra nel codice senza la sua riga.**

## 6. Git dal primo giorno

Commit piccoli e leggibili, niente lavoro fuori dal repository, niente copie
parallele che divergono.

*Il caso:* per giorni sono esistite due cartelle con lo stesso progetto a
versioni diverse, e si è creduto che il lavoro fosse andato perso.

## 7. Contraddire quando serve

Se una strada è sbagliata si dice prima, non dopo averci perso un pomeriggio.
Vale anche di fronte all'insistenza: se la risposta tecnica non cambia,
ripeterla con i dati.

*Il caso:* le estensioni Manifest V3 non filtrano in un browser pilotato. È
stato chiesto tre volte in forme diverse; la risposta giusta era mostrare la
misura, non riprovare.

## 8. I dati personali non entrano nel repository

Cronologia, preferiti, fonti e chiavi di firma restano sul disco, mai
tracciati.

*Il caso:* il primo commit conteneva `auth.key` e la cronologia dei siti
aperti — in un progetto destinato a essere pubblicato.
