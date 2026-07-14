# Low-Freq Hunter · widget menu bar per macOS

Un widget per la barra dei menu di macOS che mostra a colpo d'occhio lo stato
dei telefoni con l'app **Low-Freq Hunter**: le bande sopra soglia con i dBFS,
per più dispositivi contemporaneamente. Interroga la dashboard LAN dei telefoni
(`/api/state`).

È **un solo file** (`lowfreq.10s.py`), senza dipendenze oltre a SwiftBar e
Python 3: il renderer della barra e la finestra di configurazione sono
incorporati.

## Installazione lampo (un comando)

Con SwiftBar già installato e la sua cartella plugin su `~/Documents/SwiftBar`:

```sh
mkdir -p ~/Documents/SwiftBar && \
curl -fsSL https://raw.githubusercontent.com/Adrianss31/lowfreq-menubar/main/lowfreq.10s.py \
  -o ~/Documents/SwiftBar/lowfreq.10s.py && chmod +x ~/Documents/SwiftBar/lowfreq.10s.py
```

Poi apri SwiftBar e usa "configura…". Tutto il resto qui sotto è la versione
per passi.

## Installazione (per passi)

1. Installa [SwiftBar](https://github.com/swiftbar/SwiftBar) (una volta sola):
   ```sh
   brew install swiftbar
   ```
   Al primo avvio SwiftBar chiede una cartella per i plugin (es. `~/Documents/SwiftBar`).

2. Metti `lowfreq.10s.py` in quella cartella e rendilo eseguibile. Il modo più
   rapido, con lo script incluso:
   ```sh
   ./install.sh
   ```
   Oppure a mano:
   ```sh
   cp lowfreq.10s.py ~/Documents/SwiftBar/
   chmod +x ~/Documents/SwiftBar/lowfreq.10s.py
   ```

3. In SwiftBar apri il menu del widget → **configura…**: si apre una pagina web
   locale dove imposti l'indirizzo (e l'eventuale token) dei telefoni e scegli
   le bande da tenere d'occhio. Salva e clicca **aggiorna**.

Il `.10s.` nel nome del file è l'intervallo di refresh (10 s). Rinominalo in
`.5s.` o `.30s.` per cambiarlo.

## Aggiornare / installare su un altro Mac

È un file solo: scaricalo di nuovo nella cartella plugin di SwiftBar (o
`git pull` + `./install.sh`) e clicca "aggiorna". La configurazione
(`~/.config/lowfreq-menubar.json`, con indirizzi e token) resta locale e non
va copiata: la reimposti dalla UI sul Mac nuovo.

## Come si legge la barra

Disegnata come **template image** (SF Pro, cifre tabellari): macOS la ricolora
da sola, nera o bianca, così è leggibile su qualsiasi sfondo e in chiaro/scuro.

- **badge pieno** (pill) = banda **sopra soglia**
- testo semplice = banda sorvegliata ma tranquilla
- filetto verticale tra i dispositivi; `offline` / `fermo` scritti in chiaro

Le **bande selezionate** in configurazione sono sempre visibili con i loro dBFS
(anche sotto soglia). Se non selezioni nulla, la barra mostra solo le bande che
in quel momento superano la soglia.

## Requisiti

- macOS con SwiftBar
- Python 3 (`xcode-select --install` oppure `brew install python`)
- `osascript` (già incluso in macOS) per il rendering della barra

Nessun dato lascia la tua rete: il widget parla solo con i telefoni in LAN.
