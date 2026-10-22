"""Runtime patch for Optiland 0.6.3's Newton asphere intersection.

Phone-camera aspheres often have strong high-order terms on a base conic that a
steep ray misses. The Newton solver seeds from that base-conic intersection.
When the seed is NaN the ray is lost (CN105116519B ex.1, S13, 0.85 field:
hundreds of rays). We replace a non-finite conic seed with the vertex-plane
intersection, which lands in the basin of the aspheric root.

A second, related bug: the iteration's "all rays converged" test treats NaN
as not converged, so one dead rim ray forces every surface to run ``max_iter``
steps. Non-finite residuals are ignored for the early-exit test. The value
returned to Optiland still marks those rays as not converged.

The patch wraps ``_solve_distance_primal`` and leaves ``distance`` itself
alone, so Optiland 0.6.3's aperture argument and torch implicit-diff path
keep working. It should be proposed upstream rather than kept here forever.
"""
from __future__ import annotations

_APPLIED = False


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    import optiland.backend as be
    from optiland.geometries.newton_raphson import NewtonRaphsonGeometry, _DistanceSolveResult
    from optiland.geometries.standard import StandardGeometry

    def _solve_distance_primal(self, rays, aperture=None):
        # Same iteration as the 0.6.2 patch. Optiland 0.6.3's own Newton step
        # changes spot size on CN105116519B-ex2 (2.56 µm -> ~5.6 µm) even when
        # the plane seed is used, so the published checks would move.
        t = StandardGeometry.distance(self, rays, aperture=aperture)
        n_dir = be.where(be.abs(rays.N) > 1e-14, rays.N, 1e-14)
        t = be.where(be.isfinite(t), t, -rays.z / n_dir)
        iterations = 0
        residual = be.zeros_like(t)
        for i in range(self.max_iter):
            x_int = rays.x + t * rays.L
            y_int = rays.y + t * rays.M
            z_int = rays.z + t * rays.N
            residual = self.sag(x_int, y_int) - z_int
            if be.max(be.where(be.isfinite(residual), be.abs(residual), 0.0)) < self.tol:
                break
            nx, ny, nz = self._surface_normal(x_int, y_int)
            nz_safe = be.where(be.abs(nz) > 1e-14, nz, 1e-14)
            df_dt = (-nx / nz_safe) * rays.L + (-ny / nz_safe) * rays.M - rays.N
            t = t - residual / be.where(be.abs(df_dt) > 1e-14, df_dt, 1e-14)
            iterations = i + 1
        converged = be.logical_and(be.isfinite(residual), be.abs(residual) < self.tol)
        return _DistanceSolveResult(t=t, residual=residual, converged=converged, iterations=iterations)

    NewtonRaphsonGeometry._solve_distance_primal = _solve_distance_primal
    _APPLIED = True
