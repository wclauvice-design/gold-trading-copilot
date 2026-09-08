# Gold Trading Copilot

Un moteur de decision personnel pour le trading intraday sur l'or (XAU/USD) :
analyse technique + fondamentale automatisee, combinee en une recommandation
unique (achat / vente / attente), avec un journal de trading integre.

**Ce que cet outil fait :** il analyse le marche a votre place et vous donne
une conclusion claire avec le raisonnement complet, pour que vous n'ayez plus
a tracer des lignes ou lire des indicateurs a la main.

**Ce que cet outil ne fait pas :** il ne passe aucun ordre. Il ne se connecte
a aucun broker pour executer quoi que ce soit. Vous gardez 100% du controle :
vous lisez la recommandation, vous decidez, vous executez vous-meme chez votre
broker (MT4/MT5, plateforme web, etc.).

## Avertissement important

Aucune strategie, aussi "reputee" soit-elle, ne garantit un resultat. Cet
outil est une aide a la decision construite avec des methodes serieuses et
documentees (suivi de tendance, structure de marche, filtre macro), pas une
boite noire magique. Il peut se tromper, se tromper souvent meme sur certaines
periodes de marche. Ne tradez jamais un montant que vous ne pouvez pas vous
permettre de perdre, testez longuement en compte de demonstration avant tout
argent reel, et ne considerez rien ici comme un conseil en investissement.

## 1. Installation

Pre-requis : Python 3.10+.

```bash
cd gold-copilot
python3 -m venv venv
source venv/bin/activate        # sous Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Demarrage rapide (mode DEMO, sans aucune cle)

Le mode demo utilise des donnees simulees realistes pour que vous puissiez
tout de suite explorer le dashboard, tester le moteur de decision et le
journal de trading, sans configurer quoi que ce soit.

```bash
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Ouvrez ensuite **http://localhost:8000** dans votre navigateur.

## 3. Passer en mode LIVE (vraies donnees de marche)

### 3.1 Obtenir un acces OANDA (gratuit)

1. Creez un compte "practice" (demo, gratuit, sans depot) sur
   https://www.oanda.com -- c'est un compte de test qui donne acces a des prix
   reels en temps reel, meme sans y deposer d'argent.
2. Dans l'espace "Manage API Access" de votre compte OANDA, generez un jeton
   d'API personnel.
3. Recuperez aussi votre "Account ID" (visible dans les parametres du compte,
   format `XXX-XXX-XXXXXXX-XXX`).

Vous pourrez plus tard basculer `OANDA_ENV=live` avec un vrai compte de
trading une fois a l'aise avec l'outil -- inutile de se precipiter.

### 3.2 Obtenir une cle FRED (gratuite, optionnelle mais recommandee)

Sert uniquement au filtre macro (taux reel US 10 ans). Sans elle, ce filtre
reste neutre et l'outil fonctionne quand meme avec les 2 strategies techniques.

Inscription gratuite : https://fred.stlouisfed.org/docs/api/api_key.html

### 3.3 Remplir le fichier .env

```
APP_MODE=live
OANDA_API_KEY=votre_token
OANDA_ACCOUNT_ID=votre_account_id
OANDA_ENV=practice
FRED_API_KEY=votre_cle_fred
```

Redemarrez `uvicorn` -- le dashboard passe automatiquement sur les vraies
donnees (badge "LIVE" en haut a droite).

## 4. Le calendrier des evenements a risque

Le fichier `data/risk_calendar.json` liste les publications macro a fort
impact (NFP, decisions de taux, CPI...). Les calendriers gratuits complets
(ForexFactory, Investing.com) interdisent l'extraction automatique dans leurs
conditions d'utilisation -- la solution fiable et legale pour un usage
personnel est de mettre a jour ce fichier vous-meme, en 2 minutes chaque
dimanche soir, a partir de leur site ou de celui de la Fed
(federalreserve.gov/newsevents/calendar.htm).

Format d'une entree :

```json
{
  "datetime_utc": "2026-09-05T12:30:00",
  "event": "NFP (Nonfarm Payrolls US)",
  "currency": "USD",
  "impact": "high",
  "note": "optionnel"
}
```

Quand un evenement `"impact": "high"` tombe dans les 3 heures a venir, l'outil
affiche un bandeau d'alerte et reduit fortement la confiance de ses
recommandations (la volatilite autour de ces publications rend les
stop-loss peu fiables).

## 5. Comprendre les 3 moteurs de decision

### Strategie 1 -- Suivi de tendance (EMA / RSI / MACD)

Determine un biais de tendance sur H1 (alignement des moyennes mobiles
20/50/200), confirme si possible sur H4, puis cherche un point d'entree precis
sur M15 (pullback + retournement RSI + changement de signe du MACD). Stop
loss a 1.5x ATR(H1), objectif a 2x le risque pris. C'est l'approche la plus
"classique" et la plus robuste sur la duree : elle evite de trader contre la
tendance de fond.

### Strategie 2 -- Structure de marche / Smart Money Concepts

Repere les balayages de liquidite (le prix depasse breve­ment un plus haut ou
un plus bas recent puis revient a l'interieur -- une signature frequente sur
l'or, ou les mouvements de "chasse aux stops" precedent souvent les vrais
mouvements directionnels), puis identifie la zone d'order block laissee juste
avant le mouvement impulsif qui suit. Signal fort quand le prix revient dans
cette zone en coherence avec la structure H1.

### Strategie 3 -- Filtre macro (dollar & taux reels)

Ne donne pas de direction propre : ponder la confiance des deux strategies
techniques selon le contexte fondamental (force du dollar via un indice
"maison" calcule sur un panier de paires FX, et taux reel americain 10 ans via
la Fed). Un vent macro favorable renforce la confiance, un vent contraire la
fait chuter, et un evenement a risque imminent l'ecrase presque totalement.

### Comment les 3 se combinent

La recommandation finale n'apparait que si les 2 strategies techniques
s'accordent sur une direction ; le filtre macro vient ensuite amplifier ou
reduire la confiance de ce signal. Si la confiance finale retombe sous 35/100
(a cause d'un desaccord technique ou d'un vent macro contraire), l'outil
recommande explicitement d'attendre, meme si un signal technique existait au
depart. C'est voulu : mieux vaut rater un trade que de forcer une entree
faiblement confirmee.

## 6. Le journal de trading

Chaque recommandation peut etre consignee en un clic ("Consigner ce trade")
avec tout ce que l'outil proposait (direction, niveaux, confiance,
raisonnement complet). Une fois votre ordre reellement passe chez votre
broker, mettez a jour la ligne avec votre execution reelle, puis cloturez-la
avec le prix de sortie : le P&L et le taux de reussite se calculent seuls,
globalement et par combinaison de strategies -- de quoi savoir objectivement,
apres quelques semaines, quelle approche fonctionne vraiment pour vous sur
l'or, plutot que de se fier a une impression.

Toutes les donnees du journal restent dans le fichier local `journal.db`
(SQLite), sur votre machine uniquement.

## 7. Limites a garder en tete

- Ce n'est pas un DXY officiel : l'indice dollar est une approximation
  calculee sur 5 paires majeures (voir `app/data/dollar_index.py`).
- La detection de structure/order block est une heuristique simplifiee, pas
  une reproduction exacte d'une methode ICT/SMC complete -- elle donne une
  bonne base mais gagnera a etre affinee avec votre propre experience du
  marche.
- Le calendrier de risque depend de vos mises a jour manuelles.
- Aucune combinaison de strategies ne remplace une gestion du risque
  rigoureuse (taille de position adaptee, jamais plus de 1-2% du capital
  risque par trade).

## 8. Prochaines ameliorations possibles

- Notifications Telegram/push quand un signal a haute confiance apparait.
- Backtesting automatique des 3 strategies sur l'historique OANDA.
- Ajout d'une 4e couche optionnelle (sentiment COT report, correlation avec
  les indices actions).
- Deploiement sur un petit serveur (VPS) pour y acceder depuis votre mobile
  en dehors de votre reseau local.
