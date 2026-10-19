"""Modeles de donnees partages par le pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Listing:
    """Annonce brute normalisee, quelle que soit la source."""

    id: str
    source: str
    url: str
    titre: str
    description: str
    prix: float
    surface: float
    pieces: int
    type_bien: str                      # flat | house | building | loft
    ville: str
    code_postal: str
    categorie_ville: str = "ville_moyenne"
    zone_recherche: str = ""
    dpe: str | None = None
    ges: str | None = None
    annee_construction: int | None = None
    etage: int | None = None
    charges_copro_annuelles: float | None = None
    taxe_fonciere: float | None = None
    copro_en_procedure: bool = False
    en_copropriete: bool | None = None
    nb_lots_copro: int | None = None
    prix_a_baisse: bool = False
    date_publication: str = ""
    date_modification: str = ""
    photos: int = 0
    pro: bool = True
    exclusivite: bool = False
    neuf: bool = False
    loue_actuellement: bool = False
    loyer_actuel: float | None = None
    mode_vente: str = "classique"       # classique | enchere_judiciaire | vente_interactive | cession_etat
    mise_a_prix: float | None = None    # mise a prix / premiere offre / prix plancher
    date_vente: str = ""                # date d'audience ou d'ouverture des offres
    occupe: bool = False                # bien occupe (encheres : procedure d'expulsion a prevoir)
    prix_estime_note: str = ""          # comment le prix attendu a ete estime
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def prix_m2(self) -> float:
        return self.prix / self.surface if self.surface else 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketData:
    """Donnees de marche rattachees a la commune / arrondissement de l'annonce."""

    code_insee: str | None = None
    commune: str | None = None
    population: int | None = None
    loyer_m2: float | None = None            # loyer d'annonce charges comprises, carte des loyers
    loyer_m2_bas: float | None = None
    loyer_m2_haut: float | None = None
    loyer_nb_obs: int | None = None
    loyer_source: str = ""
    prix_m2_dvf_median: float | None = None
    prix_m2_dvf_p25: float | None = None
    prix_m2_dvf_p75: float | None = None
    dvf_nb_ventes: int | None = None
    dvf_annees: str = ""
    str_adr: float | None = None             # prix moyen par nuit observe (Inside Airbnb)
    str_occupation: float | None = None
    str_nb_annonces: int | None = None
    str_source: str = ""
    encadrement_loyers: bool = False
    changement_usage_requis: bool = False
    courte_duree_faisable: bool = True
    courte_duree_risque: int = 0            # 0 libre, 1 declaration, 2 autorisation / quotas, 3 impossible
    courte_duree_note: str = ""
    zone_tendue: bool = False
    taxe_habitation_secondaire_majoration: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
