"""Small, documented runtime patch for Optiland 0.6.x.

Phone-camera aspheres often have strong high-order terms on a base conic that a
steep marginal/chief ray *misses*. Optiland's Newton-Raphson intersection seeds
the iteration with the base-conic intersection, which is NaN in that case, so
the whole ray is lost (seen on CN105116519B ex.1 S13 at 0.85 field). We seed
with the vertex-plane intersection wherever the conic seed is not finite.
The convergence test also ignores rays that are already NaN; upstream, one
failed rim ray forces every surface to run all max_iter iterations.
This should be proposed upstream to Optiland rather than kept here forever.
"""
from __future__ import annotations

_APPLIED = False


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    import optiland.backend as be
    from optiland.geometries.newton_raphson import NewtonRaphsonGeometry
    from optiland.geometries.standard import StandardGeometry

    def distance(self, rays):
        t = StandardGeometry.distance(self, rays)
        t_plane = -rays.z / be.where(be.abs(rays.N) > 1e-14, rays.N, 1e-14)
        t = be.where(be.isfinite(t), t, t_plane)
        for _ in range(self.max_iter):
            x_int = rays.x + t * rays.L
            y_int = rays.y + t * rays.M
            z_int = rays.z + t * rays.N
            f_t = self.sag(x_int, y_int) - z_int
            # ignore rays that already failed (NaN), otherwise the loop never exits early
            if be.max(be.where(be.isfinite(f_t), be.abs(f_t), 0.0)) < self.tol:
                break
            nx, ny, nz = self._surface_normal(x_int, y_int)
            nz_safe = be.where(be.abs(nz) > 1e-14, nz, 1e-14)
            df_dt = (-nx / nz_safe) * rays.L + (-ny / nz_safe) * rays.M - rays.N
            t = t - f_t / be.where(be.abs(df_dt) > 1e-14, df_dt, 1e-14)
        return t

    NewtonRaphsonGeometry.distance = distance
    _APPLIED = True
