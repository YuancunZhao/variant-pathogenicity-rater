from __future__ import annotations

from variant_pathogenicity_rater.data_sources.online.ensembl_vep_online import EnsemblVEPOnlineProvider
from variant_pathogenicity_rater.data_sources.online.gnomad_online import GnomADOnlineProvider

__all__ = [
    "EnsemblVEPOnlineProvider",
    "GnomADOnlineProvider",
]
