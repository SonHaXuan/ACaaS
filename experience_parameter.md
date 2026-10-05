\subsection*{Per-Experiment Parameters}

\noindent\textbf{E1 (Latency, G4).} 1\,000 sequential requests from a single client; 50\,ms WAN active; policies pre-loaded. Metric: median and IQR of end-to-end decision latency.

\noindent\textbf{E2 (Throughput, G4/G2).} Concurrent load swept across five levels (50, 100, 200, 500, and 1\,000 workers; Python \texttt{ThreadPoolExecutor}), each worker issuing 20 requests (up to 20\,000 total). Metric: sustained throughput (req/s), P95 response time, zero-failure threshold enforced.

\noindent\textbf{E3 (Sync consistency, G1/Corollary~1).} Policy-batch commit to PolicyChain; synchronization latency measured to last-edge ACK. Batch sizes: 1, 5, 10, 25, 50, 100, and 200 policies (seven levels); 10 repetitions each. Metric: median $\pm$ IQR per batch size.

\noindent\textbf{E4 (Ledger overhead, G2/G5).} \emph{Baseline}: direct PostgreSQL write (tamper-evident audit log, no blockchain). \emph{ACaaS}: Hyperledger Fabric endorsement via the same gRPC client. 200 operations per configuration. Metric: per-operation latency boxplot. The Fabric overhead quantifies the cost of the tamper-evidence guarantee that the direct-DB baseline cannot provide.

\noindent\textbf{E5 (Offline resilience, G4).} WAN severed for 60\,s; edge serves 1\,000 requests from cache. Connectivity restored; Offline Queue drained. Metric: online vs.\ offline latency distribution; zero drain failures.

\noindent\textbf{E6 (Conformance suite).} Full 33-test pytest suite (20 unit tests + 5 blockchain mock tests + 8 cross-validation tests), with 21 security assertions running on the live Docker Compose stack without service mocking. The 21 security assertions cover: eventual consistency (50-update offline burst, 10 trials); $\mathsf{INV}_{\mathrm{mono}}$ enforcement (5 rollback attempts rejected); F3 hash-mismatch rejection (20 injected tampered bodies); $\mathrm{seq}_e$ gap detection (5 dropped records); drain-without-loss (50 queued records); no-direct-identifier-egress (verified via \texttt{grep}-based import-level check that no module reachable from the edge PDP response path imports \texttt{requests}, \texttt{httpx}, or \texttt{urllib} + runtime trace via \texttt{sys.addaudithook("socket.connect")}); $k$-anonymity cohort check (50 batches); import-level no-WAN-coupling of edge PDP (confirmed: \texttt{edge/lightweight-pdp/} has no WAN-touching dependency); audit-replay reconstruction end-to-end. Pass threshold: 100\%.

\noindent\textbf{E7 (Cache hit-rate, Proposition~1).} $\rho_{\mathrm{edge}}$ swept across seven evenly-spaced levels from $0.10$ to $1.00$ (step $0.15$: 0.10, 0.25, 0.40, 0.55, 0.70, 0.85, 1.00) by controlling the pre-loaded policy fraction; 1\,000 samples per setting. Predicted latency uses measured constants $T_{\mathrm{edge}}=0.393$\,ms, $T_{\mathrm{WAN}}=50$\,ms, $T_{\mathrm{cloud}}=7.81$\,ms.

\noindent\textbf{E8 (Minimizer cost, G3).} 1\,000 records per size class (small/medium/large) through all three pipeline stages; 10 warm-up runs discarded; timing via \texttt{perf\_\allowbreak counter\_\allowbreak ns}. $k$-anonymity scaling: 5\,000 records per cohort at $k \in \{5, 10, 20\}$.

\noindent\textbf{E9 (Re-identification attack, Theorem~3).} Adversary: honest-but-curious clinician with exact quasi-identifier background knowledge. Cohort: 10\,000 synthetic records; 2\,000 attack trials per $(k, R)$; $k \in \{5, 10, 20\}$ and $R = 1, \ldots, 10$ independent releases from disjoint cohorts. Baseline: $1/k$ single-release bound and cumulative $1-(1-1/k)^R$.

\noindent\textbf{E10 (Substrate ablation, Lemma~1).} Config A: ACaaS ledger (PolicyChain hash-anchor). Config B: Redis 7 Pub/Sub baseline (no body-to-hash anchoring; Redis 7-alpine running as a Docker container on the cloud host, co-located with the Fabric peers). Subscriber count swept across five levels: 1, 5, 10, 25, and 50. Tamper: policy body replaced en route while ledger entry unchanged. Metric: propagation latency and tamper-detection rate (expected: 100\% ledger, 0\% pub/sub).

\noindent\textbf{E11 (Byzantine fault, $f{=}1$).} Four-peer ensemble, \texttt{AND(Org1,Org2)} threshold. Four scenarios evaluated with 50 commit attempts per scenario (200 total): honest baseline, (a)~passive, (b)~rewind (signs outdated version), (c)~fork (signs different body). Metrics: liveness rate and $\mathsf{INV}_{\mathrm{mono}}$ violation count.

\noindent\textbf{E12 (Three-site soak, G1/G2/G4).} 720 simulated minutes ($6\times$ time compression, achieved by scaling all sleep and timer intervals by $1/6$ in the emulation harness, so the test completes in $\approx120$ real minutes); three site profiles:
\begin{itemize}[leftmargin=*, itemsep=1pt]
  \item \emph{Urban hospital ward gateway}: 18 req/min, 4 partitions (mean 5\,min each).
  \item \emph{District clinic}: 12 req/min, 12 partitions (mean 8\,min each).
  \item \emph{Mobile unit}: 8 req/min, 21 partitions (mean 12\,min each).
\end{itemize}
Workload rates represent the authorization traffic routed through a \emph{single edge gateway} serving one department or vehicle; aggregate hospital-wide traffic is covered by the throughput sweep in E2.
29 policy updates at random intervals (seed 20260704). Metrics: per-site availability, offline/stale decision counts, LogChain entry count vs.\ zero-loss threshold, peak Offline Queue backlog, maximum missed updates before Phase~C reconciliation. Results in Table~\ref{tab:s-soak}.
