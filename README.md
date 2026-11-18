# Squad Tracker

Een eigen Valorant-dashboard voor marciebeur, DennisVG en Mr Mmlk. Elk uur haalt GitHub automatisch jullie nieuwste competitive matches op, rekent de statistieken uit en zet de website opnieuw online. Je hebt geen eigen server nodig en het is gratis.

## Wat je ziet

- Per speler: winrate, K/D, ACS, ADR, HS%, KAST, clutches en vorm van de laatste matches
- Head-to-head van jullie drieën met een kroon voor de beste per statistiek
- First bloods en first deaths, trades, vroege deaths en hoe vaak je alleen sterft
- K/D in de aanval en in de verdediging
- Winrate per map, per agent en per kooptype (pistol, eco, force, full buy)
- Kills per wapen
- Een overzicht van de matches die jullie samen speelden
- Filters bovenaan de pagina:
  - **Spelers:** kies wie je vergelijkt, bijvoorbeeld alleen jij en DennisVG
  - **Matches:** alle matches, alleen de matches waarin de gekozen spelers samen in één team zaten, of alleen de matches zonder de andere vrienden
  - **Aantal:** laatste 5, 10, 20 of 50, alles, of zelf een getal invullen
  - **Modus, seizoen en map**

## Eenmalig instellen (ongeveer 15 minuten)

### 1. API-sleutel aanvragen

1. Join de Discord van HenrikDev: https://discord.com/invite/X3GaVkX2YN
2. Verifieer je account.
3. Ga naar het kanaal **#get-a-key** en kies **VALORANT (Basic Key)**.
4. Kopieer de sleutel. Die begint met `HDEV-`. **Deel hem met niemand en zet hem nergens in een bestand.**

### 2. Repository maken op GitHub

1. Maak een gratis account op https://github.com als je die nog niet hebt.
2. Klik rechtsboven op **+** en kies **New repository**.
3. Geef hem een naam, bijvoorbeeld `squad-tracker`, en kies **Public**. GitHub Pages is gratis voor openbare repositories.
4. Klik op **Create repository**.
5. Klik op **uploading an existing file** en sleep alle bestanden en mappen uit deze zip erin, inclusief de map `.github`. Klik op **Commit changes**.

> Zie je de map `.github` niet? Op Mac druk je in Finder op `Cmd + Shift + .` om verborgen mappen te tonen. Op Windows zet je in Verkenner **Verborgen items** aan.

### 3. De sleutel als geheim toevoegen

1. Ga in je repository naar **Settings → Secrets and variables → Actions**.
2. Klik op **New repository secret**.
3. Naam: `HENRIK_API_KEY`
4. Waarde: je sleutel die begint met `HDEV-`.
5. Klik op **Add secret**.

De sleutel staat nu versleuteld bij GitHub. Hij komt nooit in de code of op de website.

### 4. GitHub Pages aanzetten

1. Ga naar **Settings → Pages**.
2. Kies bij **Source** de optie **GitHub Actions**.

### 5. Eerste keer draaien

1. Ga naar het tabblad **Actions**.
2. Klik links op **Matches bijwerken** en daarna op **Run workflow**.
3. Na een paar minuten is hij groen. Je website staat dan op
   `https://<jouw-gebruikersnaam>.github.io/squad-tracker/`

De eerste keer haalt hij **de hele beschikbare geschiedenis** op, van competitive en unrated. Dat kan lang duren, omdat de gratis sleutel een limiet heeft op het aantal verzoeken per minuut. Elke run werkt daarom maximaal ongeveer 50 minuten, slaat op wat binnen is en zet de site online. De volgende run (een uur later) gaat verder waar de vorige stopte. Zie je de site na de eerste run al met een deel van de matches? Dat klopt, hij vult zich vanzelf aan.

Is de hele geschiedenis binnen, dan haalt elke run alleen nog nieuwe matches op. Eén keer per dag (rond 04:00 Nederlandse tijd) controleert hij of er nog oudere matches bijgekomen zijn bij HenrikDev.

## Aanpassen

Alles staat in `config.json`:

- **Spelers toevoegen of weghalen:** pas de lijst `players` aan. De `color` bepaalt de kleur op de site.
- **Andere modi:** pas de lijst `modes` aan, bijvoorbeeld `["competitive", "unrated", "swiftplay"]`. Op de site kies je daarna per modus.
- **Een nieuwe speler toevoegen:** voeg hem toe aan `players`. De eerste runs daarna halen ook zijn hele geschiedenis op.

## Als er iets misgaat

- **De Action is rood:** klik erop en open de stap **Nieuwe matches ophalen**. Staat er `HENRIK_API_KEY ontbreekt`, controleer dan stap 3. Staat er `HTTP 404`, controleer de naam en tag in `config.json`.
- **Een speler heeft geen matches:** zijn matchgeschiedenis is misschien privé of hij heeft recent geen competitive gespeeld.
- **De site is leeg als je hem lokaal opent:** dat klopt. Een browser laat een los bestand geen data laden. Bekijk hem via de GitHub Pages-link.
- **Na 60 dagen stopt het bijwerken:** GitHub zet geplande taken soms uit als er lang niets in een repository gebeurt. Ga dan naar **Actions** en zet de workflow weer aan.

## Goed om te weten

- **"Alle matches ooit" heeft een grens.** De API haalt de geschiedenis uit Riot, en die gaat niet eindeloos terug. Daarnaast gebruikt het script de matches die HenrikDev zelf al eerder heeft opgeslagen, die soms ouder zijn. Hoe ver je precies terugkomt, verschilt per speler. Alles wat één keer binnen is, blijft voorgoed bewaard in je repository.

De data komt van de onofficiële HenrikDev API, niet van Riot zelf. Dit project is niet gemaakt of goedgekeurd door Riot Games. Als die API verandert of stopt, werkt het bijwerken niet meer tot het script is aangepast.

## Android-app

GitHub bouwt automatisch een Android-app (.apk) die de site schermvullend laat zien, met je eigen icoon. De statistieken in de app werken zichzelf bij, net als de site.

**Eenmalig instellen**
1. Ga naar **Settings → Secrets and variables → Actions → New repository secret**.
2. Name: `ANDROID_KEYSTORE_PASSWORD`. Secret: een lang wachtwoord dat je zelf verzint, bijvoorbeeld 20 willekeurige tekens. Je hoeft het nergens anders in te vullen, maar verander het later niet, anders kun je de app niet meer bijwerken.
3. Ga naar **Actions → Android-app bouwen → Run workflow**.

**Downloaden:** https://github.com/Dovdijk/Valo-track/releases/download/app/SquadTracker.apk. Open het bestand op je telefoon en sta "installeren uit onbekende bronnen" toe als Android daarom vraagt.

**Eigen icoon:** vervang `app-icon.png` (vierkant, minstens 512 x 512 pixels) via **Add file → Upload files**. GitHub bouwt dan vanzelf een nieuwe versie. Installeer die over de oude heen. De kleur linksboven in je afbeelding wordt de achtergrondkleur van het icoon.
