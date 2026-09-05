# Survey of research-grade technical debt detection and prioritisation, with a focus on LLM-based detection (2023–2026)

Input for the tech-debt-scan v2 architecture decision. The consumer is a judge agent deriving a design for an LLM-driven, read-only Claude Code skill that scans a repository, ranks technical debt findings, and hands them to a human.

## 1. Method and sources

Searches were run across arXiv, ACM, IEEE, Springer, Wiley and Semantic Scholar for the query families in the brief. Fifty-two primary sources were fetched and read as web pages or as PDFs read locally. Seven further works could not be fetched (publisher 403 or rate limiting) and are cited only through a fetched source that reports their result, flagged "via". Every number below comes from a fetched page or PDF; where a fetched abstract lacked numbers the entry says so.

| ID | Citation | URL | Theme |
|----|----------|-----|-------|
| S1 | Sheikhaei et al. LLMs for SATD identification and classification. EMSE 2024 | https://arxiv.org/abs/2405.06806 | LLM SATD |
| S2 | Sutoyo, Capiluppi. SATD detection: a decade systematic review | https://arxiv.org/html/2312.15020 | SATD survey |
| S3 | Guo et al. MAT: simple strong SATD baseline. 2019 | https://arxiv.org/abs/1910.13238 | SATD baseline |
| S4 | Souza et al. (incl. Briand). Beyond Strict Rules: LLMs for code smell detection. 2026 | https://arxiv.org/html/2601.09873v1 | LLM smells |
| S5 | Tessa, Bochicchio, Arcelli Fontana. Architectural smells detection through LLMs. ECSA 2025 | https://link.springer.com/chapter/10.1007/978-3-032-02138-0_6 | LLM arch smells |
| S6 | Dinu et al. SmellBench: LLM agents on architectural smell repair. 2026 | https://arxiv.org/html/2605.07001 | LLM arch smells |
| S7 | Sadik, Govind. Benchmarking GPT-4.0 vs DeepSeek-V3 for smells. EASE 2025 | https://arxiv.org/abs/2504.16027 | LLM smells |
| S8 | Santana Jr. et al. LLMs detecting and correcting test smells. 2025 | https://arxiv.org/abs/2506.07594 | LLM test smells |
| S9 | Zhang et al. PEFT on code smell detection. TOSEM 2026 | https://arxiv.org/abs/2412.13801 | Fine-tuned LLM |
| S10 | Astekin et al. DebtGuardian: TD in code changes with LLMs. PROFES 2025 | https://link.springer.com/chapter/10.1007/978-3-032-12089-2_21 | LLM TD in diffs |
| S11 | Mesbah et al. Prompt-based LLMs on MLCQ. EIDWT 2025 | https://link.springer.com/chapter/10.1007/978-3-031-86149-9_42 | LLM prompting |
| S12 | Tornhill, Borg, Mones. Refactoring vs Refuctoring. CodeScene 2024 (PDF read) | https://codescene.com/hubfs/whitepapers/Refactoring%20vs%20Refuctoring%20Advancing%20the%20state%20of%20AI%20automated%20code%20improvements.pdf | LLM validation |
| S13 | Tornhill et al. ACE: validated LLM refactorings. AI-IDE 2025 | https://arxiv.org/abs/2507.03536 | LLM validation |
| S14 | Borg et al. Code for Machines: AI-friendliness and Code Health. 2026 | https://arxiv.org/abs/2601.02200 | Code health |
| S15 | Crupi et al. LLM-as-a-judge for code. 2025 | https://arxiv.org/html/2507.16587 | LLM judge |
| S16 | Jin, Chen. Systematic overcorrection in LLM code reviewers. 2026 | https://arxiv.org/abs/2603.00539 | LLM review |
| S17 | Sun et al. BitsAI-CR at ByteDance. 2025 | https://arxiv.org/abs/2501.15134 | LLM review |
| S18 | Cihan et al. Automated code review in practice. ICSE-SEIP 2025 | https://arxiv.org/abs/2412.18531 | LLM review |
| S19 | Pereira et al. CR-Bench. 2026 | https://arxiv.org/abs/2603.11078 | LLM review |
| S20 | Zeng et al. SWR-Bench. 2025 | https://arxiv.org/abs/2509.01494 | LLM review |
| S21 | Rajan. MultiVer multi-agent vulnerability detection. 2026 | https://arxiv.org/abs/2602.17875 | Multi-agent |
| S22 | Wang et al. VulAgent hypothesis-validation agents. 2025 | https://arxiv.org/abs/2509.11523 | Multi-agent |
| S23 | Iranmanesh et al. ZeroFalse. 2025 | https://arxiv.org/abs/2510.02534 | FP filtering |
| S24 | Xiong, Zhang. Sifting the Noise. 2026 | https://arxiv.org/abs/2601.22952 | FP filtering |
| S25 | Chen et al. LLM4FPM: precise and complete code context. 2024 | https://arxiv.org/abs/2411.03079 | Context design |
| S26 | Xia et al. Agentless. FSE 2025 | https://arxiv.org/abs/2407.01489 | Localisation |
| S27 | Chen et al. LocAgent. 2025 | https://arxiv.org/abs/2503.09089 | Localisation |
| S28 | Fattha et al. Exploration structure for multi-file localisation. 2026 | https://arxiv.org/abs/2606.11976 | Localisation |
| S29 | De Martino et al. PRIMES 2.0 for LLM-based repository mining. 2025 | https://arxiv.org/abs/2508.02233 | Evaluation |
| S30 | Di Nucci et al. ML smell detection: are we there yet? SANER 2018 (PDF read) | https://aserebre.win.tue.nl/SANER2018RENE.pdf | ML detectors |
| S31 | Zazworka et al. Four approaches for TD identification. SQJ 2014 | https://link.springer.com/article/10.1007/s11219-013-9200-8 | Detector overlap |
| S32 | Palomba et al. Do they really smell bad? ICSME 2014 (PDF read) | https://fpalomba.github.io/pdf/Conferencs/C3.pdf | Perception |
| S33 | Pecorelli et al. Developer-driven smell prioritisation. MSR 2020 | https://2020.msrconf.org/details/msr-2020-papers/18/Developer-Driven-Code-Smell-Prioritization | Prioritisation |
| S34 | Nayebi, Cai, Kazman et al. Paying down architectural debt. ICSE-SEIP 2019 (PDF read) | https://arxiv.org/abs/1811.12904 | Arch hotspots |
| S35 | Wiese et al. Strong change coupling and defects, Apache Aries. OSS 2015 (PDF read) | https://www.ime.usp.br/~gerosa/papers/Wiese2015_Chapter_AnEmpiricalStudyOfTheRelationB.pdf | Change coupling |
| S36 | Hrishikesh et al. Co-change graph entropy. 2025 | https://arxiv.org/abs/2504.18511 | Change coupling |
| S37 | Bird et al. Don't touch my code! ESEC/FSE 2011 (PDF read) | https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/bird2011dtm.pdf | Ownership |
| S38 | Kapser, Godfrey. Cloning considered harmful considered harmful. EMSE 2008 (PDF read) | https://plg.uwaterloo.ca/~migod/papers/2008/emse08-ClonePatterns.pdf | Duplication |
| S39 | Muñoz Barón, Wyrich, Wagner. Validation of Cognitive Complexity. ESEM 2020 | https://arxiv.org/abs/2007.12520 | Complexity |
| S40 | Lenarduzzi et al. Are SonarQube rules inducing bugs? SANER 2020 | https://arxiv.org/abs/1907.00376 | Rule validity |
| S41 | Amit. Which alert removals are beneficial? 2026 | https://arxiv.org/abs/2603.21322 | Rule validity |
| S42 | Tornhill, Borg. Code Red. TechDebt 2022 | https://arxiv.org/abs/2203.04374 | Code health |
| S43 | Borg et al. Increasing, not Diminishing. TechDebt 2024 | https://arxiv.org/abs/2401.13407 | Code health |
| S44 | Paudel et al. TD and lead time, industrial case. SEAA 2024 | https://arxiv.org/abs/2406.01578 | TD cost |
| S45 | Lenarduzzi, Besker, Taibi, Martini, Arcelli Fontana. SLR on TD prioritisation. JSS 2021 (PDF read) | https://research.chalmers.se/publication/521030/file/521030_Fulltext.pdf | Prioritisation |
| S46 | Lenarduzzi, Saarimäki, Taibi. Technical Debt Dataset. PROMISE 2019 | https://arxiv.org/abs/1908.00827 | Dataset |
| S47 | Madeyski, Lewowski. MLCQ. EASE 2020 (PDF read) | https://madeyski.e-informatyka.pl/download/MadeyskiLewowski20EASE.pdf | Dataset |
| S48 | Palomba et al. Landfill. MSR 2015 (PDF read) | https://www.cs.wm.edu/~denys/pubs/MSR'15-LandFill-CRC.pdf | Dataset |
| S49 | Ehsani, Rawal, Cai, Chatterjee. Faster Code, Deeper Debt? TOSEM 2026 | https://arxiv.org/abs/2606.14796 | TD in AI code |
| S50 | Zhu, Tsantalis, Rigby. AI-generated smells. 2026 | https://arxiv.org/abs/2605.02741 | TD in AI code |
| S51 | Paul, Zhu, Bayley. Smells of LLM generated code. 2025 | https://arxiv.org/abs/2510.03029 | TD in AI code |
| S52 | Borg. Trust calibration in IDEs. 2025 (position paper, no data) | https://arxiv.org/abs/2412.15948 | Trust |

Cited only via a fetched source: Fontana et al. 2016 (via S30); Maldonado et al. 2017 and Ren et al. 2019 (via S2); D'Ambros et al. 2009 (via S35); Mo, Cai, Kazman hotspot patterns and architecture roots (via S34); Alfayez et al. 2020 and Martini and Bosch (via S45). Li et al. 2025 (ChatGPT vs small models for SATD) and Kirbas et al. 2017 were not retrievable and are not used.

## 2. Findings

### 2a. LLM-based technical debt detection and its measured reliability

Self-admitted technical debt. The decade review (S2, 74 studies) reports median F1 on the standard comment datasets of about 0.60 for the original maximum-entropy classifier, 0.58 for the four-keyword MAT baseline (TODO, FIXME, XXX, HACK; no training, S3), 0.76 for CNNs and 0.78 for transformers. Fine-tuned Flan-T5 beat the CNN by 4.4 to 7.2 F1 points on identification, but zero-shot prompting of the largest model was 6.4 to 9.2 points worse than fine-tuning, and on classification (which debt type) the CNN beat four of six LLM configurations (S1). Surrounding code as context helped only the larger fine-tuned models (S1).

Code smells. The strongest study (S4) built an oracle from 76 developers judging 268 candidates across 30 Java projects and tested four LLMs on nine smells with zero-shot chain-of-thought prompts carrying smell definitions. LLMs reached F1 of 0.87 to 0.89 on structurally simple smells (Long Method, Large Class, Data Class) but all four scored below 0.40 on Refused Bequest, and traditional tools stayed better on context-dependent smells (JSpIRIT 0.73 on Dispersed Coupling). A hybrid of LLM plus tools improved F1 on five of nine smells but produced more false positives on complex smells, and combined voting detected more instances than the human raters on six of nine smells, which the authors call an alert-fatigue risk. The GPT-4 versus DeepSeek benchmark (S7) reports a precision-recall trade-off between models but the fetched abstract gives no numbers. On test smells, Gemini 1.5 Pro reached 74 percent (Python) and 80 percent (Java) detection accuracy, and every model sometimes introduced new smells when fixing them (S8). Parameter-efficient fine-tuning of small code models improved Matthews correlation by 0.3 to 13.7 points over prompting and heuristic baselines (S9), so prompting a frontier model is not the ceiling.

Architectural smells. Gemini 1.5 Pro detecting hub-like dependencies across 135 smells in 39 Java projects achieved 100 percent recall but 64 to 82 percent precision, and only 49 percent of its explanations were judged satisfactory (S5). SmellBench (S6) is the key cautionary result: an expert re-examining 65 hard-severity architectural smells from a static detector found 63.1 percent were intentional or acceptable design. LLM agents asked to identify those false positives agreed with the expert at kappa up to 0.94, and seven agents made zero incorrect false-positive claims. The most aggressive repair agent resolved 31 smells and introduced 140, while conservative agents netted plus 15 to 16. LLMs are currently better at judging a candidate finding than at repairing it.

Debt in diffs. DebtGuardian (S10) evaluated LLMs on MLCQ at change level; majority voting improved recall by 8.17 points, location matching needed a ten-line tolerance, and code-specialised models with larger context windows did better. Absolute precision was not in the fetched abstract.

Reliability of LLM judgement. When GPT-4-turbo judged code correctness, agreement with ground truth was kappa 0.21 (Java) and 0.10 (Python); it accepted 72 percent of correct Java code but also 50 percent of incorrect code, and 33 percent of its false rejections were "artificial hallucination", criticising statements absent from the code (S15). A 2026 study found LLM reviewers systematically reject correct implementations, and that prompts demanding explanations and fixes increased misjudgement (S16). CodeScene's benchmark on more than 100,000 real smells found only 18 to 37 percent of raw LLM refactorings preserved behaviour even though 66 to 79 percent improved the code-health metric; failures were subtle (dropped branches, inverted booleans, mishandled `this`) and invisible on inspection (S12). A layered validator (syntax, code-health delta, semantic comparison, minimal-change check) raised precision of the surviving high-confidence tier to 96.7 to 98.9 percent, and the authors attribute the gain to confidence scoring and rejection, not prompt engineering (S12, S13). Higher Code Health also predicted semantic survival of AI refactoring (S14).

Debt in AI-generated code. LLM-generated Java had 63 percent higher smell density than human reference solutions, up to 85 percent for Codex (S51). Code volume was a near-perfect predictor of structural degradation and more capable models produced more bloated, coupled code, so neither correctness nor detailed prompting prevents architectural decay (S50). A 104-source review finds LLM-assisted development amplifies code, design and documentation debt and adds fast-integration, governance, prompt, data and provenance debt, with no standard benchmarks (S49). A scanner should expect AI-authored regions to be over-represented in findings.

### 2b. Prompting and multi-agent architecture evidence

Category-specific prompting. Evidence consistently favours specialised prompts. CWE-specialised prompts "consistently outperform generic prompts" when adjudicating static-analysis warnings, reaching F1 of 0.91 and 0.96 with precision and recall above 90 percent (S23). Detailed prompts raised architectural-smell precision from 64 to 82 percent on low-severity cases (S5). The best smell study used four literature-derived questions per smell (S4). The caveat from S16 is that asking for explanations and fixes alongside the verdict raises false rejections, so specialisation belongs in the detection criteria, not in extra output obligations.

Fan-out and judge. Parallel specialised agents raise recall: a four-agent union-voting ensemble reached 82.7 percent recall against 65.7 percent for a single agent, but precision fell to 48.8 percent (S21). Voting gains appear in S10 (plus 8.17 recall) and in review aggregation (up to plus 43.67 percent F1, S20). Precision is recovered by a separate validation stage: hypothesis-validation agents cut false positives by about 36 percent (S22); agentic filtering of CodeQL alerts identified 95.5 percent of false positives at 95.5 percent precision with a strong backbone versus 36.4 percent for vanilla prompting, with gains dependent on model strength and defect class and a risk of suppressing true positives if tuned aggressively (S24). ByteDance's deployed reviewer uses this two-stage shape, RuleChecker then ReviewFilter, at 75 percent precision with a 26.7 percent ignored-comment rate (S17). Forced consultation between agents gave no measurable benefit and raised cost (S28). The evidenced pattern is fan-out for recall then an independent judge for precision, not debate.

Evidence and confidence. Every high-precision result grounded the verdict in verifiable evidence: line-level slices plus complete dependency context (S25, F1 above 99 percent on Juliet), flow traces plus context (S23), proposed fixes treated as executable counterfactuals (S16), and a semantic-equivalence check yielding a confidence tier (S12). SmellBench agents had to attach evidence to each false-positive claim and reached kappa 0.94 (S6). No fetched study isolates the effect of requiring file:line citations alone, so that specific claim is unverified; the consistent pattern is that findings anchored to concrete code artefacts survive validation.

Context and localisation. Too little and too much context both hurt: warning snippets "overly broad and cluttered with irrelevant control/data flows" while missing critical dependencies drive false positives (S25). Hierarchical localisation (file, element, line) using repository structure plus embedding retrieval outperformed autonomous agents on SWE-bench Lite at 0.70 dollars per task (S26). A code graph of files, classes, functions, imports, calls and inheritance reached 92.7 percent file-level localisation at 86 percent lower cost (S27). Domain-scoped parallel exploration beat linear exploration, and naive file-system access degraded results by over-predicting test files (S28). These favour index- or graph-guided navigation with bounded per-call context over sequential whole-file reading.

Metrics as input. No fetched study directly compares an LLM reading raw code against the same LLM given computed metrics. Indirect evidence: hybrid LLM-plus-tool strategies improved F1 on five of nine smells (S4), trace and context enrichment drove the S23 and S25 gains, and CodeScene accepts or rejects LLM output with a deterministic metric (S12). S4's verdict that the optimal strategy "depends on whether Recall or Precision is the main priority" is the honest summary.

### 2c. Classic detectors and the signals they use

Rule- and metric-threshold detectors (DECOR-style rules, JDeodorant, PMD, JSpIRIT, Organic, Arcan, Designite, DV8) remain competitive on context-dependent smells (S4). Their weaknesses are documented: low agreement between detectors and heavy threshold dependence (S30). ML detectors trained on one-smell datasets reported above 95 percent accuracy (Fontana et al. 2016, via S30), but replication with realistic mixed-smell, imbalanced data found F-measure up to 90 percent lower (S30). Four TD identification approaches (smells, static-analysis issues, modularity violations, grime) on 13 Hadoop versions had "very little overlap", and only modularity violations and dispersed coupling correlated with change- and defect-proneness (S31).

Rule validity is weak. Of 202 SonarQube Java rules only 25 had measurable fault-proneness, and rules labelled bugs were generally not fault-prone (S40). A randomised trial plus 8,245 observational alert removals found only complexity-reducing removals lowered bug tendency, by 5.5 percentage points, on about a third of files (S41). Cognitive Complexity is the one code-only metric with a validated positive correlation with comprehension time and subjective understandability across 427 snippets and roughly 24,000 evaluations, with mixed results for correctness (S39). Duplication is not uniformly harmful: 71 percent of clones in Apache httpd and Gnumeric were judged to have positive maintainability impact (S38). Not all catalogue smells were perceived as design problems by 34 respondents including original developers (S32), and a model trained on developer-perceived criticality ranked smells at F-measure up to 85 percent, beating metric-based severity (S33).

The DV8 flaw catalogue in S34 (cliques, package cycles, improper inheritance, modularity violations defined as files co-changing at least twice without a structural dependency, crossings, unstable interfaces changed with at least five dependants) combines structure with history, which is why it predicts cost.

### 2d. Git-mining signals with predictive validity

Hotspots and roots. At Brightsquid, the top 10 percent of commits by churn touched 2.5 percent of files, five architecture roots covered 80 percent of bug-fixing files, and cited literature finds five roots typically cover 50 to 90 percent of error-prone files (S34). After refactoring those roots, time to close issues in affected files fell 72 percent, bug-fix churn fell from 102 to 34 lines and bug-fix duration from 10 to 7 days, while system-wide Decoupling Level and Propagation Cost barely moved, which the authors call noise (S34). Localised flaw counts, not global metrics, tracked the improvement.

Code health times activity. Across 39 proprietary codebases and 30,737 files, low-health code had 15 times more defects, 124 percent longer time-in-development and 9 times longer maximum cycle time (S42), with the caveats of one tool and proprietary data. Returns are non-linear with amplified gains at the high-quality end, and the authors recommend preventing smells in high-churn files first (S43). A six-component industrial study using SonarQube's debt measure found mixed correlation with lead time, explaining 5 to 41 percent of variance and negative in two components (S44), so rule-count debt is a weaker predictor than health plus churn.

Change coupling. Strong change couplings in Apache Aries carried at least one defect in more than half (up to three quarters) of cases, and a model on them predicted 45.7 percent of post-release defects (S35, which also reports D'Ambros et al. 2009 finding correlation on three systems). Co-change graph entropy combined with change entropy significantly improved defect classification, raising AUROC in 82.5 percent of cases across eight Apache projects (S36).

Ownership. In Windows Vista and 7, the number of low-expertise contributors and the top owner's share related to pre- and post-release failures, and removing low-expertise contributions "dramatically decreases" contribution-based defect prediction (S37). In S34, 49.1 percent of files had a single contributor. No fetched source validates a truck-factor threshold as a debt predictor; treat bus factor as a risk modifier, not a detector.

### 2e. Prioritisation models

The JSS review (557 papers, 44 primary studies) found no consensus on factors or measures, a lack of validated tools, and little empirical evidence on principal and interest (S45). Code (38 percent), architectural (24 percent) and design debt (10 percent) dominate. Observed strategies are internal quality, productivity, correctness, cost-benefit analysis and combinations; the most concrete cost-based approach returns "the TD items that consume the largest maintenance effort" first (S45, citing Xiao et al.). Alfayez et al. classified approaches by value, cost, resource constraints and human involvement (via S45). Martini and Bosch's finding that some debt is "more dangerous" because interest spreads through dependencies motivates weighting architectural findings by fan-in (via S45). The empirically grounded prioritisation signals are change frequency (interest being paid), defect history, file code health and developer-perceived criticality of the smell type (S33, S34, S42, S43).

### 2f. Evaluation methodology and datasets

Oracles are subjective and expensive. Landfill's 243 instances across 20 projects were built by one author and validated by a second, who disputed six; the authors note that "people do not agree on the presence of a smell instance" (S48). MLCQ collected 14,739 severity reviews of 4,770 samples from 26 professional developers with no training and permission to skip uncertain samples (S47). SmellBench validators agreed at weighted kappa 0.67 (S6). S4 used 76 developers over 268 candidates. The Technical Debt Dataset offers 33 Apache Java projects with 1.8 million SonarQube issues, 38,000 smells, 28,000 SZZ-labelled faults and 57,000 refactorings for cost-oriented validation (S46).

Good practice in the fetched LLM studies is per-smell precision and recall against a multi-rater oracle (S4), kappa against experts for false-positive judgement (S6), realistic class balance (S30), and deployment metrics such as resolution rate (73.8 percent, S18), ignored-comment rate (26.7 percent, S17) and review-cycle cost (PR closure rose from 5 h 52 min to 8 h 20 min after LLM review, S18). CR-Bench warns that resolution rate hides a low signal-to-noise ratio when a reviewer is tuned to find everything (S19). PRIMES 2.0 catalogues nine threats and 25 mitigations for LLM-based repository mining, including prompt sensitivity and reproducibility (S29). SWR-Bench validated an LLM grader at about 90 percent agreement with humans (S20), so an LLM judge is acceptable for regression-testing a scanner if calibrated against a human sample.

## 3. Evidence table

| Signal or technique | What it predicts or improves | Strength of evidence | Source |
|---|---|---|---|
| Low code health in high-churn files | 15x defects, 124 percent longer time-in-development | Strong: 39 codebases; single tool | S42, S43 |
| Architecture roots and hotspots (structure plus co-change) | 80 percent of bug-fixing files in 5 roots; 72 percent faster closure after fix | Moderate: one industrial case plus cited replications | S34 |
| Strong change coupling | Over half carry a defect; predicts 45.7 percent of post-release defects | Moderate: one project plus three via D'Ambros | S35 |
| Co-change graph entropy | Significant AUROC gain in 82.5 percent of cases | Moderate: 8 Apache projects | S36 |
| Low-expertise contributors, low top-owner share | Pre- and post-release failures | Strong: Windows Vista and 7 | S37 |
| Cognitive Complexity | Comprehension time, understandability | Strong: meta-analysis, 427 snippets | S39 |
| Complexity-reducing alert removal | Minus 5.5 points bug tendency | Moderate: RCT plus observational | S41 |
| SonarQube rule violations generally | Fault-proneness | Weak: 25 of 202 rules; 5 to 41 percent of lead-time variance | S40, S44 |
| Duplication per se | Harm | Contested: 71 percent of clones beneficial | S38 |
| Modularity violations, dispersed coupling | Change- and defect-proneness | Moderate: Hadoop, 13 versions | S31 |
| Developer-perceived criticality | Ranking developers act on | Moderate: F-measure 85 percent | S32, S33 |
| Keyword SATD matching (MAT) | SATD at F1 about 0.58, no training | Strong baseline | S2, S3 |
| Fine-tuned LLM for SATD | Plus 4 to 7 F1 over CNN; zero-shot 6 to 9 below | Strong | S1 |
| LLM zero-shot on simple smells | F1 0.87 to 0.89 (Long Method, Large Class, Data Class) | Strong: 76-developer oracle | S4 |
| LLM zero-shot on context-dependent smells | F1 below 0.40 (Refused Bequest); tools better | Strong | S4 |
| LLM architectural smell detection | 100 percent recall, 64 to 82 percent precision | Preliminary: one smell type | S5 |
| Static architectural detector output | 63.1 percent false positive by expert review | Moderate: one project | S6 |
| LLM as evidence-backed false-positive judge | Kappa up to 0.94; 36 percent FP reduction; 95.5 percent FP found | Strong across security and smells | S6, S22, S24 |
| Category-specific prompts | F1 0.91 to 0.96 versus generic; precision 64 to 82 | Moderate | S5, S23 |
| Fan-out voting | Recall plus 8 to 17 points; precision falls | Moderate | S10, S21 |
| Explanation-and-fix demands in the verdict prompt | Higher false rejection | Moderate | S16 |
| LLM judging correctness unaided | Kappa 0.10 to 0.21 | Strong negative | S15 |
| Raw LLM refactoring | 18 to 37 percent behaviour-preserving | Strong: over 100,000 samples | S12 |
| Validated, confidence-tiered LLM output | 97 to 99 percent precision in high tier | Strong but vendor study | S12, S13 |
| Precise plus complete context slices | F1 above 99 percent (Juliet), 86 percent (D2A) | Strong on benchmarks | S25 |
| Hierarchical or graph-guided localisation | 92.7 percent file-level; cheaper than free agents | Strong | S26, S27, S28 |
| Forced multi-agent consultation | No gain, higher cost | Moderate | S28 |

## 4. Design recommendations for an LLM-driven read-only repository scanner

1. Rank by git-mined cost signals before reading code. Compute churn, co-change coupling, defect-fix commit density and contributor concentration per file and scan the hotspot band first. This is the best-evidenced prioritisation signal (S34, S35, S37, S42, S43) and bounds context cost.

2. Use category-specific detection prompts, each carrying the smell's definition and a few literature-derived questions, not one generic "find technical debt" prompt (S4, S5, S23). Limit the output obligation to a verdict plus evidence; do not ask for explanations and fixes in the same call (S16).

3. Separate fan-out from judgement. Run category detectors in parallel for recall, then pass every candidate to an independent judge prompt that must cite the exact lines and dependencies it relied on and may reject (S6, S17, S21, S22, S24). Expect it to remove a large share; SmellBench's 63 percent false-positive rate for detector output is the right prior.

4. Give the judge precise and complete context: the flagged span plus its callers, callees or import neighbourhood, and nothing else (S25). Navigate with a repository index or code graph and file-to-element-to-line localisation rather than sequential whole-file reading (S26, S27, S28).

5. Attach a confidence tier earned by validation steps passed, not self-reported by the model, and surface only high and medium tiers by default (S12, S13).

6. Treat structurally simple smells (long method, large class, data class, deep nesting, complex conditionals) as LLM-detectable with high precision; treat context-dependent smells (refused bequest, feature envy, dispersed coupling) as low-confidence unless a deterministic signal corroborates (S4).

7. For SATD, run a keyword matcher first and use the LLM only to classify debt type and read surrounding code for severity (S1, S2, S3).

8. Weight architectural findings by fan-in and change frequency, since interest spreads through dependencies (S34, via S45), and prefer localised flaw evidence over system-wide coupling metrics, which were insensitive even as maintenance cost fell sharply (S34).

9. Calibrate against a human sample before trusting aggregates. Build a small multi-rater oracle from the target repository, report per-category precision, and track a dismissal rate in use (S4, S17, S18, S47, S48).

10. Expect AI-generated regions to carry more debt and size-related smells (S50, S51); do not down-weight findings because code is recent.

Do not do these things; the evidence says they are unreliable:

- Do not rank by counts of generic lint or SonarQube-style violations; most rules have no measurable fault-proneness and rule-count debt explained as little as 5 percent of lead-time variance (S40, S41, S44).
- Do not flag duplication as debt by default; a majority of clones can be beneficial, so report duplication only where it co-occurs with co-change coupling (S38, S35).
- Do not let the LLM judge correctness or "is this a bug" unaided; agreement was kappa 0.10 to 0.21 and a third of false rejections were hallucinated statements (S15, S16).
- Do not propose refactorings in the scan or treat an LLM's proposed fix as evidence of the problem; raw LLM refactorings broke behaviour 63 to 82 percent of the time and aggressive repair created far more smells than it removed (S6, S12).
- Do not use a single generic prompt over whole files as the detector; precision on architectural smells was 64 percent with a shallow prompt and context clutter is a documented cause of false positives (S5, S25).
- Do not add inter-agent debate or consultation rounds expecting precision gains; the measured effect was cost without benefit (S28).
- Do not trust accuracy figures from one-smell, balanced datasets; realistic replication cut F-measure by up to 90 percent (S30).
- Do not equate zero-shot with fine-tuned performance for SATD; the gap is 6 to 9 F1 points (S1).
