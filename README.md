# Rapport de vigilance avant achat camping-car/van

Colle le texte d'une annonce (Leboncoin, La Centrale...) et obtiens un rapport structuré :
cohérence du prix, réputation étanchéité de la cellule, rappels constructeur (recherche
en direct), points de vigilance mécanique, statut du vendeur, et une checklist de
vérification physique à faire sur place.

Suite du prototype auto (`car-report-prototype/`, arrêté). Verdict business à l'origine :
**Sleep on it** (pas de canal de distribution identifié — voir
`~/.config/makerskills/business-brainstorm/archive/2026-07-24-rapport-vigilance-camping-car.md`).
Publié ici sans objectif commercial, dans l'idée qu'il puisse rendre service à quelqu'un
qui s'apprête à acheter un camping-car ou un van d'occasion.

## Usage

```bash
pip install -r requirements.txt
```

CLI :
```bash
python cli.py                              # colle le texte interactivement
python cli.py samples/ci-fourgon-2021.txt  # ou depuis un fichier
```

Interface web :
```bash
python app.py   # puis ouvrir http://127.0.0.1:5051
```

Dépendance externe : Flask uniquement. Le reste (parsing, base de connaissance, appels
API) est en stdlib Python.

## Ce qui est couvert

- **Châssis :** Fiat Ducato / Citroën Jumper / Peugeot Boxer (même plateforme Sevel),
  Ford Transit, Renault Master / Opel Movano / Nissan NV400 (même plateforme X62/X70),
  Mercedes-Benz Sprinter, Volkswagen Transporter (T5/T6/T6.1, y compris California),
  Volkswagen Crafter (y compris Grand California), Iveco Daily. Liste officielle dans
  `_CHASSIS_PATTERNS` (`parser/ad_text_parser.py`), affichée automatiquement sur la page
  et en CLI — pas besoin d'éditer ce README pour la synchroniser côté code, seulement
  pour que la doc reste lisible.
- **Cellules (réputation étanchéité) :** CI, Rapido, Hymer, Carthago, Frankia, Knaus,
  Dethleffs, Bürstner, Pilote, Chausson, Challenger, Adria, Laika, Benimar, Etrusco.
- Châssis hors liste : aucun rapport généré (pas de contenu inventé pour un véhicule hors
  scope). Cellule hors liste : dossier partiel (mécanique châssis uniquement, pas de
  réputation étanchéité).
- Tous les châssis identifiés dans le plan initial sont désormais couverts. Un
  élargissement futur à d'autres marques suivrait la même méthode (vraie recherche
  automobile par marque avant tout ajout — pas de données inventées).

## Fonctionnalités

- **Cohérence prix** : comparaison à des fourchettes indicatives par marque × type de
  carrosserie × année.
- **Réputation étanchéité** de la cellule, avec confiance affichée (`documenté` vs
  `anecdotique, à vérifier`).
- **Rappels constructeur en direct** : interroge l'API ouverte RappelConso
  (data.economie.gouv.fr, DGCCRF) par marque/modèle de châssis, en plus du renvoi vers
  rappel.conso.gouv.fr pour la vérification officielle par numéro de série.
- **Statut du vendeur** : détecte professionnel vs particulier (signaux forts uniquement :
  n° SIRET, mention explicite), et rappelle les implications légales (garantie légale de
  conformité côté pro, vice caché uniquement entre particuliers). Si un SIRET est détecté,
  recherche en direct l'entreprise (recherche-entreprises.api.gouv.fr — Sirene/INSEE) :
  raison sociale, adresse du siège, ancienneté, statut actif/radié.
- **Points de vigilance mécanique** par châssis (courroie de distribution, EGR/FAP...).
- **Checklist de vérification physique** (17 points) : documents (carte grise/VIN,
  certificat de situation administrative, contrôle technique, HistoVec), extérieur/châssis,
  moteur, étanchéité, équipements, essai routier.

Les appels réseau (RappelConso, recherche entreprises) sont *best-effort* : si l'API est
injoignable, le rapport le signale et continue sans planter.

## Différence avec le prototype auto

- Deux bases de connaissance à combiner (châssis + cellule) au lieu d'une seule.
- Fourchettes de prix indexées par type de carrosserie (fourgon/capucine/profilé/intégral) × année, pas seulement par année.
- Section "checklist de vérification physique" : contrairement à un rappel officiel (vérifiable via RappelConso), l'état d'étanchéité réel ne peut être confirmé qu'en inspectant le véhicule.

## Limites connues

- Les données de réputation étanchéité (`knowledge/cellule/*.json`) viennent d'une recherche rapide (articles de blog/SEO, essais indépendants), pas de forums spécialisés recoupés directement — tout est tagué `anecdotal`, à revérifier avant de trancher.
- Les fourchettes de prix sont indicatives, pas une cote fiable.
- La recherche RappelConso se fait par marque/modèle, pas par numéro de série (VIN) : elle ne certifie jamais qu'un véhicule précis est concerné, seulement qu'une campagne existe pour ce modèle.
- **Détection du type de carrosserie peu fiable sur Leboncoin** : confirmé sur une vraie annonce (`samples/rapido-c50-reelle-leboncoin.txt`, un Rapido C50 qui est en réalité un profilé). Le champ "Type" de Leboncoin utilise une catégorie large qui ne correspond pas à la sous-classification fourgon/capucine/profilé/intégral nécessaire pour les fourchettes de prix. Volontairement non "corrigé" en devinant un mapping approximatif qui aurait pu induire en erreur sur ce cas réel précis. Sans type détecté, le rapport annonce honnêtement "non évaluable" plutôt que d'inventer une cohérence prix fausse.

## Déploiement / sécurité

`app.py` lance Flask avec `debug=True`, pratique en local mais **à ne jamais exposer tel
quel sur un serveur accessible depuis internet** : le débogueur Werkzeug permet
l'exécution de code arbitraire. Pour un déploiement public, désactiver `debug` et servir
via un serveur WSGI de production (gunicorn, waitress...).

**Déployé en ligne sur Vercel** : https://campingcar-report-prototype.vercel.app —
Vercel importe directement l'objet `app` de `app.py` via son runtime Python (`app.run()`
n'est jamais appelé, donc `debug=True` ne s'exécute pas en production). Config dans
`vercel.json` (timeout de fonction à 30s, pour laisser de la marge aux appels RappelConso/
recherche entreprise). Les fichiers statiques vivent dans `public/static/` (pas
`static/` à la racine) : Vercel les sert directement via son CDN, comme documenté sur
[vercel.com/docs/frameworks/backend/flask](https://vercel.com/docs/frameworks/backend/flask).
Un push sur `main`/`master` redéploie automatiquement (repo GitHub connecté).

## Licence

MIT — voir [LICENSE](LICENSE).
