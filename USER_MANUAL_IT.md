# EMtranscriber Manuale Utente (Italiano)

Questo manuale descrive il comportamento attuale di EMtranscriber sulla base della codebase corrente.
E' pensato per utenti finali e power user che vogliono una vista completa di UI e logica applicativa.

## 1. Cosa Fa EMtranscriber

EMtranscriber e' un'app desktop per trascrizione offline con:

- Riconoscimento vocale automatico (ASR) tramite faster-whisper
- Diarizzazione speaker tramite pyannote
- Allineamento speaker-testo
- Revisione e modifica della trascrizione
- Export in `md`, `txt`, `json` e `srt`

L'app e' basata su una coda sequenziale (un solo job attivo alla volta), con pannello di elaborazione integrato e workflow di revisione.

## 2. Panoramica Finestra Principale

La finestra principale contiene:

- Etichetta header (`EMtranscriber - Trascrizione offline`)
- Toolbar superiore
- Pannello immagine laterale sinistro
- Tabella job
- Pannello elaborazione integrato (in basso)

### 2.1 Toolbar Superiore (Da Sinistra a Destra)

Ordine attuale:

1. `Nuovo Job`
2. `Aggiorna`
3. `Avvia coda` o `Riprendi coda` (etichetta dinamica)
4. `Pausa coda`
5. `Sospendi a fine coda` (toggle radio non esclusivo)
6. `Impostazioni`
7. `Crediti`

### 2.2 Comportamento Immagine Laterale

- Immagine idle/successo: `welcome`
- Durante elaborazione attiva: ciclo immagini ogni 2 minuti:
  - `working1`, `working2`, `working3`, `working4`, `working5`, `tired`, `panic`, `desperate`, `fail`, `destruction`
- Immagine a fine coda:
  - `welcome` per esito positivo
  - `sad` per esito non positivo

### 2.3 Tabella Job

Colonne visibili:

- `Registrazione` (o `Project` in base alla lingua UI)
- `Stato`
- `Creato`
- `Completato`
- `Sorgente`

Colonne interne nascoste:

- `Job ID`
- `Project ID`

Altri comportamenti:

- Selezione singola riga
- Righe non editabili
- Doppio click sulla riga: apre Revisione
- La selezione viene preservata durante refresh/progress quando possibile

## 3. Modello Stati Job

Stati possibili:

- `CREATED`
- `QUEUED`
- `PREPARING_AUDIO`
- `TRANSCRIBING`
- `DIARIZING`
- `ALIGNING`
- `READY_FOR_REVIEW`
- `COMPLETED`
- `PARTIAL_SUCCESS`
- `FAILED`
- `CANCELLED`

Visualizzazione stato in tabella quando in coda:

- Coda attiva: `IN_CODA (posizione/totale)`
- Coda in pausa: `IN_CODA - IN_PAUSA (posizione/totale)`

## 4. Logica Coda e Controlli

### 4.1 Regole Base della Coda

- Coda FIFO per data creazione
- Un solo job attivo alla volta
- Stato coda: `running` o `paused`
- Un job in coda parte solo se:
  - coda in stato running
  - nessun job attivo
  - almeno un job `QUEUED`

### 4.2 `Avvia coda` / `Riprendi coda`

- Etichetta dinamica:
  - `Avvia coda` quando la coda non e' in pausa
  - `Riprendi coda` quando la coda e' in pausa
- Pulsante abilitato solo quando:
  - esiste almeno un job in coda
  - non c'e' un job attivo
- Se premuto senza job attivi e senza coda:
  - appare messaggio informativo "nessun job attivo o in coda"

### 4.3 `Pausa coda`

- Abilitato solo quando esiste un job attivo
- Con job attivo, apre dialog a 3 scelte:
  - `Si`: mette in pausa la coda dopo il job attivo
  - `No`: mette in pausa la coda e annulla subito il job attivo
  - `Annulla`: non cambia nulla
- Se non c'e' job attivo ma ci sono queued (caso raro), la coda puo' comunque essere messa in pausa per logica interna

### 4.4 `Sospendi a fine coda`

- Se attivo, a fine coda (nessun worker attivo e nessun queued) l'app richiede sospensione Windows
- Usa API Windows (`SetSuspendState`)
- Se la chiamata fallisce, mostra warning
- Su piattaforme non Windows la sospensione non e' disponibile

### 4.5 Recovery Startup Job Interrotti

All'avvio, i job lasciati in stati attivi vengono rimessi in `QUEUED`:

- `PREPARING_AUDIO`
- `TRANSCRIBING`
- `DIARIZING`
- `ALIGNING`

In questo modo la coda recupera automaticamente dopo crash/interruzioni.

## 5. Menu Contestuale Riga Job (Click Destro)

Azioni visibili:

1. `Avvia`
2. `Apri revisione`
3. `Rimuovi dalla coda`
4. Separatore
5. `Elimina job`

Logica abilitazione azioni:

- `Avvia`: abilitato solo per `CREATED` o `QUEUED` non in esecuzione
- `Apri revisione`: abilitato per qualunque job selezionato
- `Rimuovi dalla coda`: abilitato solo per `QUEUED`
- `Elimina job`: abilitato solo se il job non e' in esecuzione

Comportamento visivo:

- Le azioni non valide appaiono disabilitate (grigie)

Comportamento azioni:

- `Avvia`: mette in coda il job e prova ad avviarlo subito se consentito
- `Apri revisione`: apre o porta in primo piano la finestra di revisione
- `Rimuovi dalla coda`: imposta stato `CANCELLED`, completed=true, con messaggio "Removed from queue by user."
- `Elimina job`: hard delete dati job da DB (bloccato se running)

### 5.1 Scope Eliminazione DB

`Elimina job` rimuove:

- riga job (`jobs`)
- context hints (`job_context_hints`)
- speaker (`speakers`)
- segmenti trascrizione (`transcript_segments`)
- parole trascrizione (`transcript_words`)

Se la finestra revisione del job e' aperta, viene chiusa.

## 6. Finestra Nuovo Job

Titolo: `Nuovo Job - EMtranscriber`

### 6.1 Campi

- `File sorgente` + `Sfoglia`
- `Cartella output` + `Sfoglia`
- `Progetto`
- `Lingua`
- `Modello ASR`
- `Dispositivo`
- `Tipo compute`
- Gruppo `Numero speaker`
- Gruppo `Context hints (opzionale)`

### 6.2 Sorgente e Output

- Il file sorgente e' obbligatorio
- La cartella output e' opzionale
  - Se vuota, default = cartella del file sorgente
- Se il path output esiste ma non e' una cartella, la creazione job fallisce

### 6.3 Lingua

Valori disponibili:

- `auto`
- `it`, `en`, `es`, `fr`, `de`

Comportamento language hint:

- Se lingua non e' `auto`, viene passata anche come `language_hint` nei context hints

### 6.4 Modello ASR / Device / Compute

- Modelli: `small`, `medium`, `large-v3` + eventuali chiavi extra da path configurati
- Device: `auto`, `cpu`, `gpu`
- Compute: `auto`, `float16`, `int8`

### 6.5 Modalita' Numero Speaker

Modalita':

- `auto`
- `exact`
- `minmax`

Attivazione campi:

- `exact` abilita solo exact speaker
- `minmax` abilita min e max
- `auto` disabilita i campi numerici

Validazione:

- In `minmax`, `min` deve essere <= `max`

### 6.6 Gruppo Context Hints

Toggle:

- `Applica context hints ad ASR`

Quando abilitato, vengono salvati:

- `Contesto dominio`
- `Hotwords`
- `Glossario`
- `Partecipanti attesi`
- `Acronimi attesi`
- `Entita' attese`

Parsing input:

- Campi lista in CSV separati da virgola
- Elementi vuoti rimossi
- Spazi trimmati

Se toggle disattivo:

- I context hints non vengono salvati per quel job

### 6.7 Prefill Nuovo Job

Se esiste almeno un job precedente, la finestra precompila:

- progetto
- device
- compute
- speaker mode e numerici
- toggle hints e valori hints
- lingua iniziale con euristica:
  - usa lingua selezionata precedente se valida
  - puo' usare lingua rilevata precedente se lingua selezionata era `auto`

### 6.8 Conferma

Flusso creazione job:

1. Validazione campi
2. Creazione/recupero progetto
3. Creazione job (`CREATED`)
4. Salvataggio context hints (se attivi)
5. Refresh tabella e selezione job creato
6. Controllo runtime requirements
7. Enqueue del job

## 7. Runtime Requirements e Startup

### 7.1 Primo Avvio

Al primo avvio (settings o DB mancanti), si apre automaticamente Impostazioni con focus su token Hugging Face.

### 7.2 Controlli Runtime

Verifiche eseguite:

- `faster_whisper`
- `ctranslate2`
- `torch`
- `torchaudio`
- `pyannote.audio`
- `ffmpeg` (warning non critico)
- configurazione accesso pyannote (warning non critico se manca token/path)

Se mancano requisiti critici:

- la trascrizione reale e' bloccata
- viene mostrato report dettagliato
- l'app puo' proporre avvio script `install_ml_runtime.ps1`

### 7.3 Warning Modalita' Stub

Se app in modalita' stub:

- compare warning dedicato
- risultati solo demo, non trascrizione reale

## 8. Pannello Elaborazione (Integrato in Basso)

Elementi UI:

- Titolo (`Elaborazione Job - {job}`)
- Label stage/status
- Progress bar (0..100)
- Area log con timestamp
- Pulsante `Annulla`

Comportamento:

- Si collega al job attivo all'avvio processing
- Inserisce intestazione log con config job e hints
- Riceve progress dai worker event
- Aggiunge heartbeat log se lo stage non cambia per >= 20s
- A fine/cancel/fail:
  - progress=100
  - pulsante annulla disabilitato
  - aggiunge log runtime totale

Cancel:

- Invia richiesta annullamento al worker
- Worker termina il processo figlio se ancora attivo

## 9. Modello Worker e Affidabilita'

Ogni job gira in subprocess isolato:

- Build frozen: `EMtranscriber.exe --run-job <job_id>`
- Dev mode: `python -m emtranscriber.main --run-job <job_id>`

Il processo UI legge eventi JSON da stdout figlio:

- `progress`
- `finished`
- `error`

Vantaggi:

- Migliore isolamento crash per singolo job
- UI principale piu' resiliente e reattiva

## 10. Finestra Revisione

Titolo: `Revisione trascrizione - {job}`

Si apre da:

- doppio click riga job
- menu contestuale `Apri revisione`
- apertura automatica dopo fine job per stati `COMPLETED`, `PARTIAL_SUCCESS`, `READY_FOR_REVIEW`

### 10.1 Modalita' Pending Review

Se il documento trascrizione non e' ancora disponibile:

- la finestra si apre comunque
- pannello configurazione job visibile
- tabelle segmenti/speaker vuote
- status label in stato pending
- azioni disabilitate:
  - `Salva modifiche segmenti`
  - `Salva mappatura speaker`
  - `Riesporta`

### 10.2 Toolbar Revisione

- `Aggiorna`
- `Salva modifiche segmenti`
- `Salva mappatura speaker`
- `Riesporta`
- status label a destra (`Segmenti: X | Speaker: Y` o messaggio pending)

### 10.3 Pannello Configurazione Job

Mostra in read-only:

- progetto
- file sorgente
- cartella output
- lingua selezionata e rilevata
- modello ASR, device, compute
- tempo esecuzione
- speaker mode
- stato toggle hints
- valori hints

### 10.4 Tabella Segmenti

Colonne:

- Controlli play
- Inizio
- Fine
- Speaker
- Testo

Comportamento:

- Inizio/fine/speaker non editabili
- Testo editabile
- Pulsanti play/stop su ogni segmento

Salvataggio:

- salva solo righe modificate
- imposta `source_type='edited'` sui segmenti modificati

### 10.5 Tabella Mappatura Speaker

Colonne:

- Chiave speaker (read-only)
- Nome visualizzato (editabile)

Salvataggio:

- salva solo righe modificate
- aggiorna sia `speakers.display_name` sia `transcript_segments.speaker_name_resolved`

### 10.6 Riproduzione Audio in Revisione

Richiede:

- file media sorgente presente in una delle cartelle candidate `source`
- backend multimedia PySide disponibile

Se non disponibile:

- play/stop disabilitati
- tooltip con motivazione

### 10.7 Riesporta

`Riesporta` rigenera e salva:

- `transcript.md`
- `transcript.txt`
- `transcript.json`
- `transcript.srt`

Mostra dialog con i path generati.

## 11. Finestra Impostazioni

Titolo: `Impostazioni - EMtranscriber`

Sezioni attuali:

1. `Default`
2. `Percorsi locali modelli ASR (opzionale)`
3. `Provisioning modello diarization`

Dettagli:

- altezza fissa basata sul contenuto
- pulsanti `OK` e `Cancel`

### 11.1 Sezione Default

- Lingua interfaccia:
  - Default di sistema
  - Inglese
  - Spagnolo
  - Tedesco
  - Francese
  - Italiano
- Tema interfaccia:
  - Chiaro
  - Scuro
- Modello ASR predefinito
- Dispositivo predefinito
- Compute predefinito

### 11.2 Sezione Percorsi ASR

Path locali opzionali per:

- `small`
- `medium`
- `large-v3`

### 11.3 Sezione Provisioning Diarization

- percorso locale pyannote
- token Hugging Face (masked)

### 11.4 Effetti Salvataggio Impostazioni

Su `OK`:

- salva su `settings.json`
- applica tema subito
- se cambia lingua UI, mostra messaggio di riavvio per applicazione completa

## 12. Finestra Crediti

Accesso da pulsante `Crediti`.

Contiene:

- profilo autore
- link esterni (GitHub, Website, LinkedIn)
- sezione About
- sezione licenza con `Visualizza licenza`

Se apertura link fallisce, appare warning.

## 13. Output e Layout Cartelle

Per ogni job vengono create:

- `base`
- `source`
- `working`
- `raw`
- `merged`
- `exports` (coincide con `base`)

Layout moderno tipico:

`<output_root>/EMtranscriber/<YYYYMMDD_HHMMSS>/`

File principali:

- `source/<nome_file_originale>`
- `working/working_audio.wav`
- `raw/asr_output.json`
- `raw/diarization_output.json`
- `merged/transcript.json`
- `transcript.md`
- `transcript.txt`
- `transcript.json`
- `transcript.srt`

## 14. Dati App, Impostazioni e Log

Risoluzione cartella base dati:

1. Variabile env `EMTRANSCRIBER_HOME` (se presente)
2. Build frozen: `<cartella_exe>/data`
3. Dev mode Windows: `%APPDATA%\\EMtranscriber`

Dentro la base dir:

- `emtranscriber.db`
- `settings.json`
- `logs/`
- `cache/`
- `models/`
- `projects/`

Log:

- `logs/emtranscriber.log`
- `logs/emtranscriber-crash.log` (diagnostica crash nativa via `faulthandler`)

## 15. Logica Hints in ASR/Diarization

Gli hints vengono trasformati cosi':

- `Domain context`, `Expected participants`, `Glossary + Hotwords`, `Expected acronyms`, `Expected entities`, `Language hint`
  -> merge in `initial_prompt` (max 800 caratteri)
- `Hotwords`
  -> passate anche come parametro hotwords dedicato ASR

Suggerimenti pratici:

- usa liste brevi e precise
- metti in hotwords solo termini veramente critici
- mantieni il contesto dominio conciso

## 16. Significato Stati Finali

- `COMPLETED`: pipeline completa riuscita
- `PARTIAL_SUCCESS`: output utilizzabile ma con copertura/qualita' ridotta (es. diarization fallita o pipeline stub)
- `FAILED`: errore runtime non recuperabile
- `CANCELLED`: annullamento da utente

## 17. Scenari Comuni

### 17.1 "Avvia/Riprendi coda non fa nulla"

Comportamento atteso quando:

- non ci sono job in coda
- c'e' gia' un job attivo
- ci sono requisiti runtime critici non soddisfatti

### 17.2 "Apri revisione si apre ma non vedo trascrizione"

Comportamento valido in pending mode:

- configurazione job visibile
- azioni su trascrizione disabilitate finche' i dati non sono disponibili

### 17.3 "Rimuovi dalla coda disabilitato"

Atteso se il job selezionato non e' `QUEUED`.

### 17.4 "Elimina job disabilitato"

Atteso se il job e' in esecuzione.

## 18. Note Comportamentali UI

- I job sono mostrati dal piu' recente al meno recente (`created_at DESC`).
- L'ordine di dispatch della coda e' FIFO tra i job `QUEUED`.
- Il doppio click su qualunque riga apre Revisione.
- Le azioni del menu contestuale sono state-aware.
- Alla chiusura app con job attivi, l'app chiede conferma e puo' bloccare la chiusura se lo shutdown worker non e' ancora completato.

---

Manuale generato in base al comportamento corrente della codebase.
