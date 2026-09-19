# Space JEPA 2 hypercomplex mathematics and physics specification

Date: 2026-09-19  
Status: prospective design specification; equations are not performance evidence  
Working engine name: **APENic Quaternion Predictive-Memory JEPA (AQPM-JEPA)**  
Application name: **Space JEPA 2**

Authoritative implementation sequence:
[`SPACE_JEPA_2_FINAL_EXECUTION_CHECKLIST_2026-09-19.md`](SPACE_JEPA_2_FINAL_EXECUTION_CHECKLIST_2026-09-19.md).

## 1. Scope and non-negotiable boundary

This specification defines an APENic JEPA upgrade to the existing transient
detection pipeline. **Space JEPA 2 is the full detector and discovery workflow;
AQPM-JEPA is the internal predictive and anomaly-analysis engine.** The engine
consumes point-in-time photometric evidence and returns forecasts, anomaly traces,
memory-support diagnostics and physical residuals to the pipeline's candidate
assembly and review stages.

The pipeline retains ingestion, calibration, quality control, identity resolution,
catalogue checks, evidence binding, review queues and reporting gates. The upgraded
engine is allowed to reprioritize candidates or replace an expensive legacy detector
stage only after a common-cohort evaluation proves that doing so preserves useful
transients at the frozen review budget.

This specification does not claim that hypercomplex arithmetic, episodic memory, or
a physics head improves transient discovery. Each is retained only if a frozen
ablation establishes useful value for the end-to-end detection pipeline.

Formally, for the point-in-time alert stream $\mathcal D_{\leq t}$, the engine emits

$$
\mathcal E_t=
\operatorname{AQPMJEPA}(\mathcal D_{\leq t})
=\{\widehat Z_{t,h},s_{t,h}^{(k)},u_{t,h},r_{t,h}^{\rm phys},m_{t,h}\},
$$

where $\widehat Z$ is the future latent forecast, $s^{(k)}$ are preserved anomaly
components, $u$ is predictive uncertainty, $r^{\rm phys}$ is the physical residual
and $m$ is memory support. The existing pipeline combines $\mathcal E_t$ with
heuristic, template, catalogue and provenance evidence to create a review priority:

$$
R_t=\operatorname{Rank}_{\rm frozen}
(\mathcal E_t,E_t^{\rm heuristic},E_t^{\rm template},E_t^{\rm catalogue},
E_t^{\rm provenance}).
$$

$R_t$ is a queue priority, not a discovery probability. The pipeline's operational
endpoint is useful transient retrieval at fixed review budget, with time-to-detection,
false alerts and missed rare-event families reported explicitly.

The available checkout currently implements TNS **search** for registry identity and
position checks. It does not ingest TNS object photometry. The official TNS Get Object
API can request associated photometry and spectra, but that is a separate endpoint and
data contract. TNS public-object CSVs primarily provide registry metadata such as name,
position, discovery date/magnitude, redshift and type. A registry row or a single
discovery magnitude is not a light curve.

Space JEPA 2 therefore requires three explicitly separated data roles:

1. **Survey/broker photometry** supplies the point-in-time light curve used as model
   input. ZTF/ALeRCE is the natural first path in this repository.
2. **TNS registry metadata** supplies name resolution, discovery and classification
   outcomes, redshift when present, and timestamps needed to prevent label leakage.
3. **TNS object photometry**, if the user dataset includes it, is an additional
   heterogeneous photometric source. It must be unit-, filter-, calibration- and
   provenance-qualified before merging with survey photometry.

No model is trained until the supplied “TNS data” is classified into these roles and
passes the schema in Section 3.

## 2. Why quaternions, and where they are allowed

### 2.1 Algebra choice

Use the quaternion algebra

$$
\mathbb H = \{q=q_0+q_1\mathbf i+q_2\mathbf j+q_3\mathbf k:q_r\in\mathbb R\},
$$

with

$$
\mathbf i^2=\mathbf j^2=\mathbf k^2=\mathbf i\mathbf j\mathbf k=-1.
$$

Quaternions are selected because they are associative, have a conjugation and norm,
have mature real-component implementations, and impose structured coupling among
four real components. Quaternion neural networks have previously used the Hamilton
product to model internal relations in multidimensional signals. That prior work
motivates an experiment; it does not establish suitability for astronomy.

For

$$p=p_0+p_1\mathbf i+p_2\mathbf j+p_3\mathbf k,$$
$$q=q_0+q_1\mathbf i+q_2\mathbf j+q_3\mathbf k,$$

the left Hamilton product used everywhere in this model is

$$
\begin{aligned}
p\otimes q={}&(p_0q_0-p_1q_1-p_2q_2-p_3q_3)\\
&+(p_0q_1+p_1q_0+p_2q_3-p_3q_2)\mathbf i\\
&+(p_0q_2-p_1q_3+p_2q_0+p_3q_1)\mathbf j\\
&+(p_0q_3+p_1q_2-p_2q_1+p_3q_0)\mathbf k.
\end{aligned}
$$

Conjugation and norm are

$$
\bar q=q_0-q_1\mathbf i-q_2\mathbf j-q_3\mathbf k,
\qquad
\lVert q\rVert_{\mathbb H}^2=q\bar q=\sum_{r=0}^3q_r^2.
$$

For pure quaternions $u=(0,\mathbf u)$ and $v=(0,\mathbf v)$,

$$
u\otimes v=(-\mathbf u\cdot\mathbf v,\;\mathbf u\times\mathbf v).
$$

This gives the intended decomposition for a three-axis spectral representation:
the scalar part measures aligned spectral coherence, while the imaginary part
preserves oriented color disagreement. The latter would be discarded by an ordinary
dot product or by immediate mean pooling.

### 2.2 What is rejected

- **Octonions are rejected for v1.** Their non-associativity makes layer composition,
  memory retrieval and reproducibility harder without a demonstrated data symmetry.
- **Dual quaternions are rejected.** They represent rigid transformations; a light
  curve is not a rigid-body pose.
- **Lorentz or spacetime Clifford equivariance is rejected.** “Space” in Space JEPA
  does not make sky photometry a Lorentz-equivariant learning problem.
- **Full Clifford multivectors are deferred.** Clifford layers are justified when
  the inputs and desired outputs carry a known orthogonal group action. TNS/ZTF
  scalar photometry does not currently provide that requirement. They may become
  relevant to image cutouts or vector-valued physical simulations in a later study.

The hypercomplex branch must be compared with a parameter-matched real-valued branch.
If its gain is absent, the quaternion constraint is removed.

## 3. Required data contract

Each photometric row must have:

| Field | Meaning | Rule |
|---|---|---|
| `entity_id` | Canonical physical-source identity | Required; aliases resolve to one entity before splitting. |
| `source_id` | Survey/TNS source identifier | Required and namespace-qualified. |
| `observation_id` | Stable exposure/measurement identity | Required for replay and duplicate rejection. |
| `observed_at_mjd` | Observation time | Finite; strictly point-in-time available. |
| `available_at_mjd` | Time the row became available to the model | Required; must not exceed scoring cutoff. |
| `survey` | Originating observing system | Required. |
| `band` | Exact passband identifier | Required; bound to response-curve version. |
| `value` | Signed flux, calibrated flux density, or magnitude | Missing only for an explicit non-detection. |
| `value_error` | One-sigma statistical uncertainty | Positive when a measurement is present. |
| `value_kind` | `flux`, `flux_density`, `difference_flux`, or `magnitude` | Required; incompatible kinds are not pooled. |
| `unit` | Physical or declared instrumental unit | Required. |
| `is_detection` | Detection state | Required for flux-like data. |
| `limiting_value` | Limiting flux/magnitude for non-detection | Required when a limit is used in a likelihood. |
| `calibration_id` | Zeropoint/reduction identity | Required. |
| `ra_deg`, `dec_deg` | ICRS position | Required for identity and context, not latent dynamics. |

Each object-level TNS record must preserve:

| Field | Use |
|---|---|
| `tns_name`, `tns_objid` | Registry identity only. |
| `discovery_mjd`, `discovery_mag`, `discovery_band` | Historical registry evidence; not a substitute for a light curve. |
| `redshift`, `redshift_error`, `redshift_source`, `redshift_available_mjd` | Optional physical conditioning, available only after its timestamp. |
| `classification`, `classification_source`, `classification_mjd` | Outcome label; never an input before the classification time. |
| `host_id`, `host_redshift`, `host_association_probability` | Optional context with explicit association uncertainty. |
| `last_modified`, response digest, query time | Versioning and replay. |

The frozen dataset manifest records row counts, object counts, band counts, detection
and limit counts, missingness, units, calibration versions, label maturity, aliases,
time range, hashes and all rejected rows with reasons.

## 4. Observation mathematics

### 4.1 Magnitude and flux

When the input is an AB magnitude $m$ with error $\sigma_m$, convert to flux density

$$
f_\nu=f_{\nu,0}10^{-0.4m},
\qquad f_{\nu,0}=3631\ \mathrm{Jy},
$$

$$
\sigma_{f_\nu}=\frac{\ln 10}{2.5}f_\nu\sigma_m.
$$

This conversion is used only when the magnitude system is verified. Difference flux
remains signed. A non-detection is not converted to zero flux.

For a scoring prefix ending at cutoff $t_c$, robust normalization is fitted only to
permitted prefix observations:

$$
a_c=\operatorname{median}\{f_i:i\leq c,\delta_i=1\},
$$

$$
s_c=\max\left(1.4826\operatorname{MAD}(f_{i\leq c}),
\operatorname{median}(\sigma_{i\leq c}),s_{\min}\right),
$$

$$
x_i=(f_i-a_c)/s_c,\qquad u_i=\sigma_i/s_c.
$$

The raw calibrated values, $a_c$ and $s_c$ remain in the artifact so the physical
decoder can operate in physical units. Changing any future value must leave every
prefix token unchanged.

### 4.2 Time

For observation $i$,

$$
\Delta t_i=t_i-t_{i-1},\qquad
\tau_i=t_i-t_{\mathrm{first,prefix}}.
$$

Model inputs use stable transforms such as $\log(1+\Delta t_i)$ and
$\log(1+\tau_i)$. If a redshift $z$ was available by the cutoff, the physical head
also uses rest-frame phase

$$
\tau_{i,\mathrm{rest}}=\frac{t_i-t_0}{1+z}.
$$

An estimated or missing redshift has a separate availability/error channel. It is
never silently set to zero.

### 4.3 Passband basis and quaternion token

For the initial ZTF $g,r,i$ experiment, fix the imaginary axes by increasing
effective wavelength:

$$
\mathbf e_g=(1,0,0),\quad
\mathbf e_r=(0,1,0),\quad
\mathbf e_i=(0,0,1).
$$

A detected single-band value produces the pure spectral quaternion

$$
c_i=0+x_i(e_{b_i,1}\mathbf i+e_{b_i,2}\mathbf j+e_{b_i,3}\mathbf k).
$$

For more than three bands, response curves are projected onto three orthonormal
spectral modes fitted on training metadata only, or represented in multiple
quaternion blocks. A learned arbitrary band permutation is not called a physical
symmetry.

The complete token contains $d_q$ quaternion channels:

$$
Q_i=\phi_{\mathrm{scalar}}(\log(1+\Delta t_i),\log(1+\tau_i),u_i,
\delta_i,m_i) + \phi_{\mathrm{spectral}}(c_i),
$$

where scalar covariates enter real components and spectral flux enters imaginary
components. All quantities are dimensionless before addition. Missingness $m_i$ and
detection $\delta_i$ remain explicit real gates.

## 5. Quaternion encoder

### 5.1 Linear map

For $Q\in\mathbb H^{d_{\rm in}}$ and
$W\in\mathbb H^{d_{\rm out}\times d_{\rm in}}$,

$$
(W\star Q)_a=\sum_b W_{ab}\otimes Q_b+B_a.
$$

All layers use left multiplication in this order. A quaternion weight has four real
parameters rather than the 16 independent entries of an unconstrained real
$4\times4$ mixing block. Comparisons must therefore match both trainable parameters
and compute, not only the nominal hidden width.

### 5.2 Direction-preserving activation and normalization

Avoid component-wise split activations as the only nonlinearity. Use a real radial
gate that preserves quaternion direction

$$
\operatorname{QGate}(q)=\sigma(a\lVert q\rVert_{\mathbb H}+b)
q,
$$

with a learned real gain and an identity residual. Quaternion RMS normalization is

$$
\operatorname{QRMSNorm}(Q)=
\gamma\frac{Q}{\sqrt{d_q^{-1}\sum_a\lVert Q_a\rVert_{\mathbb H}^2+\epsilon}},
$$

where $\gamma$ is real unless a quaternion gain is explicitly ablated.

### 5.3 Causal quaternion attention

Queries, keys and values are quaternion projections. The attention logit is real:

$$
\ell_{ij}=
\frac{1}{\sqrt{4d_h}}
\sum_{a=1}^{d_h}\operatorname{Re}
\left(Q_{ia}\otimes\overline{K_{ja}}\right)
+b_{\Delta t_{ij}}+b_{b_i,b_j},
$$

$$
A_{ij}=\frac{\exp(\ell_{ij})\mathbf 1[j\leq i]}
{\sum_{r\leq i}\exp(\ell_{ir})},
\qquad
O_i=\sum_{j\leq i}A_{ij}V_j.
$$

The causal mask is mandatory for forecasting. Padding, unavailable observations and
post-cutoff observations receive zero attention probability.

The model also retains the imaginary interaction

$$
\Omega_{ij}=\operatorname{Im}
\sum_a Q_{ia}\otimes\overline{K_{ja}},
$$

as a color-orientation diagnostic. It is not silently reduced to the scalar attention
logit.

## 6. Continuous-time predictive state

The discrete encoder produces a posterior state after each observation,
$Z(t_i^+)\in\mathbb H^{d_q}$. Between observations, a causal quaternion-valued flow
evolves the state:

$$
\frac{dZ}{dt}=F_\theta(Z,t,C),
$$

$$
F_\theta(Z,t,C)=A_\theta(Z,t,C)\star Z+Z\star B_\theta(Z,t,C)+U_\theta(t,C).
$$

Left and right products are both explicit because quaternions do not commute. The
ODE is integrated in its four real components with shared quaternion-constrained
parameters. At an observation,

$$
Z(t_i^+)=Z(t_i^-)+\operatorname{Update}_\theta(Z(t_i^-),Q_i).
$$

This hybrid jump-flow form separates continuous evolution from measurement updates.
A transformer-only time-conditioned predictor is the mandatory simpler baseline.
If the flow does not improve held-out forecasting enough to justify its solver cost,
it is removed.

Interpolation used to construct controls must be online/causal. Natural cubic
interpolation using future samples is forbidden in point-in-time scoring.

For forecast horizon $h$, the base predictor returns

$$
\widehat Z^{(0)}_{c,h}=\Phi_{\theta,h}(Z(t_c^+),C_c).
$$

## 7. JEPA target and loss

The online/context encoder has parameters $\theta$. The target encoder has parameters
$\xi$ updated only by exponential moving average:

$$
\xi\leftarrow m_s\xi+(1-m_s)\theta,
$$

where $m_s$ follows a frozen cosine schedule from $0.996$ to $0.9999$ over planned
optimizer steps.

For a future target window $Y_{c,h}$ that was never visible to the context encoder,

$$
Z^*_{c,h}=\operatorname{sg}\left(E_\xi(Y_{c,h})\right).
$$

With quaternion vectors realified as $\mathcal R(Z)\in\mathbb R^{4d_q}$, the primary
latent loss is

$$
\mathcal L_{\rm JEPA}=
\frac{1}{\sum_{c,h}w_{c,h}}
\sum_{c,h}w_{c,h}
\operatorname{SmoothL1}\left(
\operatorname{Norm}(\mathcal R(\widehat Z_{c,h})),
\operatorname{Norm}(\mathcal R(Z^*_{c,h}))
\right).
$$

Weights depend only on target availability and declared uncertainty, never on the
test label. Horizon-specific losses are retained rather than averaged away.

Collapse controls operate on the realified batch representation:

$$
\mathcal L_{\rm var}=\frac{1}{4d_q}\sum_r
\max(0,\gamma-\sqrt{\operatorname{Var}(Z_r)+\epsilon})^2,
$$

$$
\mathcal L_{\rm cov}=\frac{1}{4d_q}
\sum_{r\neq s}\operatorname{Cov}(Z)_{rs}^2.
$$

Their weights are frozen from development data. Effective rank, component variance,
quaternion norm and scalar/imaginary energy ratios are always reported.

## 8. APEN-derived episodic residual memory

### 8.1 Memory contents

Each permitted training entry $m$ stores

$$
M_m=(K_m,R_{m,h},g_m,t_m,\pi_m),
$$

where $K_m$ is a detached causal quaternion key, $R_{m,h}$ is a future latent
residual, $g_m$ is the physical source/alias group, $t_m$ is the cutoff and $\pi_m$
is the survey/calibration/population contract.

The residual is refreshed against the current frozen base predictor:

$$
R_{m,h}=Z^*_{m,h}-\widehat Z^{(0)}_{m,h}.
$$

Validation/test objects never write to memory. Entries sharing a query's physical
source, alias group, or prohibited later time are masked.

### 8.2 Learned distance and retrieval

For query key $K$ and memory key $K_m$, use a positive diagonal metric over
quaternion channels:

$$
\rho_a=\frac{\operatorname{softplus}(w_a)}
{d_q^{-1}\sum_r\operatorname{softplus}(w_r)},
$$

$$
d_m(K)=\frac{1}{d_q}\sum_{a=1}^{d_q}
\rho_a\lVert K_a-K_{m,a}\rVert_{\mathbb H}^2.
$$

With eligibility mask $\mathcal A(K,m)$,

$$
\alpha_m=
\frac{\exp(-d_m/T)\mathcal A(K,m)}
{\sum_r\exp(-d_r/T)\mathcal A(K,r)},
$$

$$
R^{\rm mem}_{h}=\sum_m\alpha_mR_{m,h}.
$$

The context-only gate receives distance, retrieval entropy, coverage, cadence and
population compatibility:

$$
g_h=\sigma\left(G_\psi(K,h,d_{(1)},H(\alpha),C_c)\right),
$$

$$
\widehat Z_{c,h}=\widehat Z^{(0)}_{c,h}+g_hR^{\rm mem}_{h}.
$$

The gate cannot access the future target, class label, TNS outcome or test error.
Base and corrected forecasts are both saved.

### 8.3 Mandatory memory controls

- memory off;
- fixed uniform metric;
- shuffled residual values;
- shuffled keys;
- wrong-population memory;
- gate fixed closed;
- gate fixed open;
- no source-group exclusion attack; and
- nearest-neighbor kernel regression with the same bank.

Memory is retained only if it beats no-memory by the frozen minimum effect and its
gain disappears under destructive controls while surviving the kernel baseline.

## 9. Physics-informed state and decoder

### 9.1 Scope

There is no universal low-dimensional optical transient physics model. Supernovae,
tidal disruption events, cataclysmic variables, AGN, kilonovae and artifacts do not
share one valid expanding-photosphere law. The physics branch is therefore a gated
auxiliary hypothesis for compatible, sufficiently observed sources. It is never a
hard constraint on all TNS objects.

The physical state distribution is

$$
X(\tau)=\left(\log R_{\rm ph},\log T_{\rm eff},\log E_{\rm int},
\log t_{\rm diff},v/c,A_V,\eta_{\rm host}\right),
$$

with positivity enforced by exponential or softplus transforms. The decoder predicts
a distribution over $X$, not a single certain parameter vector.

### 9.2 Expanding photosphere and diffusion surrogate

For compatible events, use

$$
\frac{dR_{\rm ph}}{d\tau}=v(\tau),
\qquad V=\frac{4\pi}{3}R_{\rm ph}^3,
\qquad P=\frac{E_{\rm int}}{3V},
$$

$$
\frac{dE_{\rm int}}{d\tau}
=Q_{\rm in}(\tau)-\frac{E_{\rm int}}{t_{\rm diff}}
-P\frac{dV}{d\tau},
$$

$$
L_{\rm bol}=\frac{E_{\rm int}}{t_{\rm diff}},
\qquad
T_{\rm eff}=\left(
\frac{L_{\rm bol}}{4\pi\sigma_{\rm SB}R_{\rm ph}^2}
\right)^{1/4}.
$$

$Q_{\rm in}$ is a nonnegative learned input function unless a separately specified
physical family is tested. It must not be called radioactive, magnetar or fallback
power without that family-specific model and data.

### 9.3 Spectral energy distribution and redshift

The Planck function is

$$
B_\nu(\nu,T)=\frac{2h\nu^3}{c^2}
\left[\exp\left(\frac{h\nu}{k_BT}\right)-1\right]^{-1}.
$$

For an isotropic blackbody photosphere,

$$
L_{\nu_e}(\nu_e,\tau)=4\pi^2R_{\rm ph}^2B_\nu(\nu_e,T_{\rm eff}).
$$

Using luminosity distance $D_L(z)$ and $\nu_e=(1+z)\nu_o$,

$$
F_{\nu_o}(\nu_o,t_o)=
\frac{1+z}{4\pi D_L(z)^2}L_{\nu_e}((1+z)\nu_o,\tau)
10^{-0.4[A_{\rm MW}(\nu_o)+A_{\rm host}((1+z)\nu_o)]}.
$$

The band prediction is computed through the versioned transmission curve $T_b$ and
the declared photon- or energy-counting convention:

$$
\mu_b(t)=\mathcal C_b\left[F_{\nu_o}(\cdot,t),T_b,\mathrm{zeropoint}_b\right]
+F_{{\rm host},b},
$$

where $F_{{\rm host},b}$ is omitted for difference photometry. The implementation
must be checked against a trusted synthetic-photometry package; factors of $1+z$,
frequency/wavelength Jacobians and zeropoints require unit tests.

### 9.4 Detection and censoring likelihood

For a measured flux $y_i$, use a robust Student-$t$ likelihood

$$
s_i^2=\sigma_i^2+\sigma_{{\rm floor},b_i}^2+\sigma_{{\rm model},i}^2,
$$

$$
\mathcal L_{\rm det,i}=-\log t_\nu(y_i;\mu_i,s_i).
$$

For an upper limit $\ell_i$ under the corresponding noise model,

$$
\mathcal L_{\rm lim,i}=-\log
T_\nu\left(\frac{\ell_i-\mu_i}{s_i}\right),
$$

where $T_\nu$ is the Student-$t$ CDF. A limit is never treated as a detection at the
limiting flux.

### 9.5 Physics residuals

When required quantities are identifiable, define

$$
\mathcal L_{\rm SB}=
\left[\log L_{\rm bol}-\log(4\pi\sigma_{\rm SB}R_{\rm ph}^2T_{\rm eff}^4)\right]^2,
$$

$$
\mathcal L_{\rm expansion}=\left|
\frac{R_{j+1}-R_j}{\Delta\tau_j}-v_j
\right|^2,
$$

$$
\mathcal L_{\rm energy}=\left|
\frac{E_{j+1}-E_j}{\Delta\tau_j}
-Q_{{\rm in},j}+L_{{\rm bol},j}
+P_j\frac{V_{j+1}-V_j}{\Delta\tau_j}
\right|^2.
$$

Each term has an availability and compatibility mask. Sparse one-band data generally
cannot identify $R$, $T$, extinction and distance simultaneously; in that regime the
physics head must return broad uncertainty or `not_identifiable`, not a confident fit.

## 10. Full training objective

The development objective is

$$
\begin{aligned}
\mathcal L={}&
\lambda_J\mathcal L_{\rm JEPA}
+\lambda_O(\mathcal L_{\rm det}+\mathcal L_{\rm lim})
+\lambda_V\mathcal L_{\rm var}
+\lambda_C\mathcal L_{\rm cov}\\
&+\lambda_P(\mathcal L_{\rm SB}+\mathcal L_{\rm expansion}
+\mathcal L_{\rm energy})
+\lambda_G\mathcal L_{\rm gate}.
\end{aligned}
$$

Proposed development defaults are

| Weight | Initial value | Rule |
|---|---:|---|
| $\lambda_J$ | 1.0 | Primary representation objective. |
| $\lambda_O$ | 0.25 | Applied only to calibrated observable targets. |
| $\lambda_V$ | 0.10 | Collapse prevention. |
| $\lambda_C$ | 0.01 | Off-diagonal covariance control. |
| $\lambda_P$ | 0.05 | Compatibility-masked physics regularization. |
| $\lambda_G$ | 0 initially | No gate sparsity until its effect is diagnosed. |

These weights may be tuned on development train/validation only, then frozen. Report
each component in physical units and normalized units; a lower combined loss cannot
hide a worse forecast endpoint.

## 11. Anomaly mathematics

For every newly observed target token, let

$$e^{(0)}=\mathcal R(Z^*-\widehat Z^{(0)}),\qquad
e^{(m)}=\mathcal R(Z^*-\widehat Z).$$

Fit robust training-only covariance $\Sigma_h$ and define predictive surprise

$$
s_{\rm pred}=e^{(0)\top}(\Sigma_h+\epsilon I)^{-1}e^{(0)}.
$$

The memory-corrected surprise is

$$
s_{\rm corr}=e^{(m)\top}(\Sigma_h+\epsilon I)^{-1}e^{(m)}.
$$

Quaternion angular disagreement is

$$
s_{\rm angle}=1-
\frac{\sum_a\operatorname{Re}
(Z^*_a\otimes\overline{\widehat Z^{(0)}_a})}
{\lVert Z^*\rVert\lVert\widehat Z^{(0)}\rVert+\epsilon}.
$$

The oriented spectral disagreement retained from pure-quaternion components is

$$
s_{\rm wedge}=\left\|
\operatorname{Im}\sum_a Z^*_a\otimes
\overline{\widehat Z^{(0)}_a}
\right\|.
$$

Memory unsupportedness and disagreement are

$$
s_{\rm support}=d_{(1)},\qquad
s_{\rm entropy}=-\sum_m\alpha_m\log(\alpha_m+\epsilon),
$$

$$
s_{\rm route}=\lVert\widehat Z-\widehat Z^{(0)}\rVert_{\mathbb H}.
$$

The normalized physical residual is

$$
s_{\rm phys}=\frac{
\mathcal L_{\rm det}+\mathcal L_{\rm lim}+\lambda_P\mathcal L_{\rm physics}}
{N_{\rm available}}.
$$

These components are preserved separately. Object summaries use maximum, high
quantile, time integral, consecutive-run length and per-band maxima:

$$
S_{\max}=\max_j s_j,
\quad S_{0.95}=Q_{0.95}(s_j),
\quad S_{\rm area}=\sum_j s_j\Delta t_j.
$$

They do not use only a mean. A scalar queue rank, if needed, is a frozen monotone
model trained on development data. It is explicitly not a discovery probability.

## 12. Forecast and intervention protocol

Primary observer-frame horizons are proposed as 1, 3, 7 and 14 days. For sources
with cutoff-available redshift, corresponding rest-frame horizons are reported as an
auxiliary analysis. Each horizon has its own coverage count and loss.

The intervention experiment defines an external forcing $U(\tau)$ over
$[\tau_a,\tau_b]$:

$$
\frac{dX}{d\tau}=f(X,\tau)+B(X,\tau)U(\tau).
$$

Evaluate separately:

1. pre-intervention forecast;
2. response while $U\neq0$;
3. autonomous evolution after $U=0$; and
4. time to return to the reference manifold, when such a manifold is defined.

For real survey light curves, “intervention” may be a controlled injection into
archived backgrounds. It must not be described as a physical intervention on the
astronomical source. A natural forcing claim requires a source class with a justified
physical mechanism and observed forcing proxy.

## 13. Initial model configuration

Proposed development configuration:

| Component | Value |
|---|---:|
| Quaternion width | 64 quaternion channels = 256 real components |
| Encoder blocks | 6 |
| Attention heads | 8 |
| Predictor blocks | 3 |
| Dropout | 0.10 |
| Forecast horizons | 1, 3, 7, 14 observer-frame days |
| Target EMA | cosine 0.996 to 0.9999 |
| Optimizer | AdamW |
| Learning rate | $3\times10^{-4}$ |
| Weight decay | $10^{-4}$ |
| Gradient clip | 1.0 |
| Memory temperature | validation-selected, frozen before test |
| Memory capacity | set from training cohort only; every source group receives deterministic coverage before repeats |
| Numerical precision | float32 model; float64 metrics/covariance/physics integration checks |

Batch size, maximum token count, solver tolerance and memory capacity depend on the
actual TNS/survey dataset inventory and hardware pilot. They must be recorded, not
silently inferred. Long curves are never truncated without a versioned policy that
preserves early limits, first detection, extrema, recent points and the discarded-row
manifest.

## 14. Required comparisons

Every reported result includes:

1. existing SIDEREA heuristic;
2. current template detector;
3. persistence, linear and quadratic extrapolation;
4. matched GRU;
5. matched real-valued causal Transformer;
6. real-valued predictive JEPA;
7. quaternion predictive JEPA without continuous flow;
8. quaternion predictive JEPA with continuous flow;
9. AQPM-JEPA without memory;
10. full AQPM-JEPA;
11. full AQPM-JEPA without physics loss; and
12. nearest-neighbor residual correction with the same memory bank.

Match information, parameter count, optimization steps and selection rules. Report
wall time and peak memory. A quaternion model winning only because it has more real
components or a memory model winning because it sees additional objects is invalid.

## 15. Identifiability and failure states

The model emits reason-coded states:

- `forecast_available`;
- `insufficient_history`;
- `unsupported_band_contract`;
- `calibration_mismatch`;
- `memory_support_absent`;
- `redshift_unavailable`;
- `physics_not_identifiable`;
- `physics_incompatible_population`;
- `target_not_yet_observed`;
- `out_of_population_support`; and
- `numerical_failure`.

Important degeneracies include:

- radius-temperature-distance degeneracy;
- extinction-temperature/color degeneracy;
- host flux versus transient baseline;
- redshift versus time-scale and color evolution;
- cadence gaps versus genuine rapid evolution; and
- memory similarity versus shared survey artifact.

Missing information is not set to zero. The physics loss is disabled when its
required quantities are unavailable, while the empirical forecast route may still
operate.

## 16. Verification obligations

### Algebra tests

- Hamilton product matches the explicit real matrix expansion.
- $q\bar q=\lVert q\rVert^2$ and norm multiplicativity hold within tolerance.
- Left/right multiplication order is tested with noncommuting examples.
- Pure-quaternion products recover dot and cross components.
- Real-valued reference implementation matches quaternion layers exactly.
- Gradients pass finite-difference checks.

### Causality and data tests

- Changing any post-cutoff value leaves every prefix representation unchanged.
- Alias-equivalent sources cannot cross a split or enter their own memory retrieval.
- TNS classifications and redshifts are available only after their recorded times.
- Causal interpolation never reads the next observation.
- Non-detections use censored likelihood and are never converted to detections.

### Physics tests

- AB magnitude/flux conversions round trip.
- Synthetic blackbodies recover band fluxes against an independent implementation.
- Frequency- and wavelength-domain integrals agree after Jacobian conversion.
- Rest/observer time and frequency transforms pass analytic cases.
- Stefan-Boltzmann, expansion and energy residuals vanish on constructed solutions.
- Non-identifiable single-band cases return a failure state or broad posterior.

### Evidence tests

- Base and memory-corrected forecasts are both retained.
- Token-level surprise reconstructs every object summary.
- Checkpoint, memory, data, response-curve and code digests are verified.
- Partial or failed grids cannot produce aggregate success metrics.
- The current TS-JEPA and v1 shadow-pilot artifacts replay unchanged.

## 17. Promotion criteria

Hypercomplex arithmetic advances only if it improves the frozen primary endpoint
over the parameter/compute-matched real model and does not worsen calibration or
population-shift behavior beyond the prespecified margin.

Physics advances only if it improves observable forecasting or scientifically useful
diagnostics on compatible sources, passes posterior predictive checks, and remains
well calibrated. Plausible-looking $R$ or $T$ curves are not evidence.

Memory advances only if it beats no-memory and kernel retrieval by the frozen useful
effect, while shuffled/wrong-population controls destroy the gain.

The full model advances to prospective shadow operation only after all three claims
are evaluated separately. A failure in one component removes that component rather
than being hidden inside an aggregate score.

## 18. Implementation modules

The mathematical design maps to:

- `src/siderea/ml/quaternion.py`: algebra, layers, normalization and attention;
- `src/siderea/ml/prequential.py`: causal prefixes and targets;
- `src/siderea/ml/space_jepa_v2.py`: encoder, flow, target encoder and predictor;
- `src/siderea/ml/episodic_memory.py`: memory contracts and residual retrieval;
- `src/siderea/ml/physics.py`: state decoder, passband synthesis and likelihoods;
- `src/siderea/ml/space_jepa_v2_train.py`: objective, selection and checkpointing;
- `src/siderea/ml/space_jepa_v2_evaluate.py`: forecasts and anomaly evidence;
- `src/siderea/clients/tns_object.py`: read-only Get Object adapter, only if the
  supplied data require live retrieval;
- `src/siderea/research/space_jepa_v2_protocol.py`: frozen protocol validation; and
- `src/siderea/research/space_jepa_v2_benchmark.py`: complete-grid execution.

No existing TS-JEPA checkpoint format or historical result is overwritten.

## 19. Primary references

- Assran et al., [Self-Supervised Learning from Images with a Joint-Embedding
  Predictive Architecture](https://arxiv.org/abs/2301.08243).
- Parcollet et al., [Quaternion Recurrent Neural
  Networks](https://arxiv.org/abs/1806.04418).
- Ruhe, Brandstetter and Forre, [Clifford Group Equivariant Neural
  Networks](https://arxiv.org/abs/2305.11141).
- Kidger et al., [Neural Controlled Differential Equations for Irregular Time
  Series](https://arxiv.org/abs/2005.08926), and Morrill et al., [Neural CDEs for
  Online Prediction Tasks](https://arxiv.org/abs/2106.11028).
- Guillochon et al., [MOSFiT: Modular Open-Source Fitter for
  Transients](https://arxiv.org/abs/1710.02145).
- Hogg, [Distance Measures in Cosmology](https://arxiv.org/abs/astro-ph/9905116).
- Budavari and Szalay, [Probabilistic Cross-Identification of Astronomical
  Sources](https://arxiv.org/abs/0707.1611).
- Boone, [Avocado: Photometric Classification of Astronomical Transients with
  Gaussian Process Augmentation](https://arxiv.org/abs/1907.04690).
- Iskandarli et al., [Anomaly Hunter for Alerts](https://arxiv.org/abs/2602.12955).
- Transient Name Server, [TNS 2.0 Search/Get Objects API
  manual](https://www.wis-tns.org/sites/default/files/api/tns2_manuals/TNS2.0_APIs_manual.pdf).

## 20. Immediate next action

Before implementation, run a read-only inventory of the user's TNS dataset and emit
one machine-readable report answering:

1. Is it the public-object table, Get Object output, spectra, survey photometry, or a
   joined dataset?
2. How many objects have two, three, five and ten or more usable epochs?
3. Which bands, units, magnitude systems, zeropoints and upper-limit conventions occur?
4. How many redshifts and classifications were known by each scoring cutoff?
5. Can TNS identities be joined to ZTF/ALeRCE objects without ambiguous aliases?
6. Which source populations are large enough for train A, validation A, test A-later
   and shifted test B?

The dataset inventory determines whether the full hypercomplex/physics model is
identifiable, whether only the empirical predictive route is currently feasible, or
whether additional survey photometry must be obtained first.
