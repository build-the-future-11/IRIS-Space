"""Scientific feature extraction for IRIS observations.

The public functions in this package deliberately return plain dictionaries and
data frames.  That keeps feature products easy to serialize in run manifests and
allows the same code to consume broker records, CSV rows, or pandas data frames.
"""

from .photometry import (
    PhotometryFeatureConfig,
    compute_grouped_photometry_features,
    compute_photometry_features,
    flatten_photometry_features,
)

__all__ = [
    "PhotometryFeatureConfig",
    "compute_grouped_photometry_features",
    "compute_photometry_features",
    "flatten_photometry_features",
]
