# Deliverable 6: Analytical Note & Mathematical Formulation
## Student Submission Template — TECH5 Collaborative Project

**Team:** [Team Name / Group Number]  
**Authors (Team B - Assignment Engine):** [Student Names & IDs]  
**Authors (Team A - Visualization & Recommender):** [Student Names & IDs]  
**Course:** TECH5 Programming & Application Design, NHH Norwegian School of Economics  
**Date:** [Submission Date]

---

> [!IMPORTANT]
> **Instructions for Students:**  
> This document serves as the formal deliverable template for **Deliverable 6 (Analytical Note)** as defined in Section 15 and Section 6 of the TECH5 project specification (`projectTech5.tex`).  
>
> Replace all bracketed text `[...]` with your team's mathematical formulation, indicator derivations, decision criteria, and critical reflections. Maintain rigorous mathematical notation and explain how your analytical design translates directly into your Python implementation in `app/engine/solvers.py` and `app/engine/metrics.py`.

---

## 1. Problem Definition & Mathematical Modeling Approach

### 1.1 Business Context & Decision Dilemma
*Describe the real-world allocation challenge faced by academic coordinators. Discuss the inherent conflict between collective project quality (skill matching) and individual student satisfaction (preference rank).*

[Provide a 1–2 paragraph summary of the problem, referencing Rezaeinia et al. (2022) for context without copying their proprietary algorithm.]

### 1.2 Chosen Assignment Methodology & Academic Justification
*Identify your approved assignment methodology (e.g., Integer Linear Programming with PuLP/CBC, stable matching variant, heuristic search, or bipartite min-cost flow).*

[State your chosen method, explain why it is appropriate for this problem scale, and justify its computational feasibility within a single-process Python application.]

---

## 2. Mathematical Formulation

### 2.1 Index Sets & Dimensions
Define the primary index sets used throughout your mathematical model:
- $S = \{s_1, s_2, \dots, s_n\}$: Set of students in the cohort ($|S| = n$).
- $P = \{p_1, p_2, \dots, p_m\}$: Set of available semester projects ($|P| = m$).
- $K = \{k_1, k_2, \dots, k_q\}$: Set of evaluated technical skills ($|K| = q$).
- $F \subseteq S \times P$: Set of pre-allocated fixed assignment pairs $(s, p)$.
- $K_p = \{k \in K : \text{req}_{p,k} > 0\} \subseteq K$: Set of skills required by project $p$.
- $K_p^{M} = \{k \in K_p : m_{p,k} = 1\} \subseteq K_p$: Set of skills that are mandatory for project $p$.
- $Q_{p,k} = \{s \in S : \text{skill}_{s,k} \ge \text{req}_{p,k}\}$: Set of students who meet project $p$'s requirement for skill $k \in K_p$.
- $\mathcal{A} = \{A^{(1)}, \dots, A^{(t)}\}$: List of previously found allocations, where each $A^{(i)} = \{(s,p) \in S \times P : x^{(i)}_{s,p} = 1\}$ contains exactly $|S|$ pairs. It starts empty and grows by one allocation per solve.
- *[Define any additional sets your model introduces]*

### 2.2 Model Parameters
Formally define all input parameters, units, and ranges:
- $l_p \in \mathbb{Z}_{\ge 0}$: Minimum headcount capacity for project $p$.
- $u_p \in \mathbb{Z}_{\ge 1}$: Maximum headcount capacity for project $p$ ($l_p \le u_p$).
- $L \in \{1, \dots, |P|\}$: Maximum number of projects a student may rank (the length of the preference list; $L = |P|$ if students rank everything).
- $r_{s,p} \in \{1, 2, \dots, L\} \cup \{|P|+1\}$: Rank that student $s$ gave to project $p$ (1 = most preferred). Students rank only some projects; a project that student $s$ did not rank gets the penalty rank $r_{s,p} = |P|+1$.
- $w_{s,p}^{\text{pref}}$: Preference score derived from rank $r_{s,p}$ (Borda count over the ranked list):
  $$w_{s,p}^{\text{pref}} = \max\bigl(0,\ L - r_{s,p} + 1\bigr) \in \{0, 1, \dots, L\}, \qquad \tilde w_{s,p} = \frac{w_{s,p}^{\text{pref}}}{L} \in [0, 1]$$
  *Explanation: A first choice scores $L$, the last allowed rank scores $1$, and any unranked project scores $0$ because $r_{s,p} = |P|+1 > L$. A student who ranks fewer than $L$ projects is handled by the same formula. The normalized score $\tilde w_{s,p}$ lies on the same scale as the skill-fit score $\sigma_{s,p}$, which makes the weight $\lambda$ in Strategy 3 meaningful.*
- $\text{skill}_{s,k} \in \{0, 1, 2, 3, 4, 5\}$: Declared proficiency level of student $s$ in skill $k$.
- $\text{req}_{p,k} \in \{1, 2, 3, 4, 5\}$ for $k \in K_p$: Stated requirement level of project $p$ for skill $k$. Skills outside $K_p$ carry no requirement ($\text{req}_{p,k} = 0$).
- $m_{p,k} \in \{0, 1\}$ for $k \in K_p$: Binary flag indicating if skill $k$ is mandatory for project $p$.
- $d \in \mathbb{Z}_{\ge 1}$: Minimum number of students whose project must differ between any two alternative solutions ($d = 1$ in the specification).
- $\sigma_{s,p} \in [0, 1]$: Normalized skill-fit score of student $s$ assigned to project $p$:
  $$\sigma_{s,p} = \begin{cases} \dfrac{1}{|K_p|} \displaystyle\sum_{k \in K_p} \min\!\left(1, \dfrac{\text{skill}_{s,k}}{\text{req}_{p,k}}\right) & K_p \ne \emptyset \\[2ex] 1 & K_p = \emptyset \end{cases}$$
  *Explanation: Each required skill contributes the fraction of the requirement the student covers, capped at 1 so that surplus proficiency does not compensate for a gap elsewhere. A project with no requirements is fully compatible with every student.*
- $\varepsilon \in (0, \tfrac{1}{|S|+1}]$: Small tie-breaking constant used in Strategies 1 and 2.
- $\lambda \in [0, 1]$: Weight on preference versus skill fit in Strategy 3 ($\lambda = 0.5$ by default).
- $\mu \ge 0$: Penalty on the worst assigned rank in Strategy 1 ($\mu = 0$ switches the penalty off).

### 2.3 Decision Variables
Define your optimization decision variables:
- $x_{s,p} \in \{0, 1\}$: Binary decision variable equal to $1$ if student $s$ is assigned to project $p$, and $0$ otherwise.
- $y_p \in \{0, 1\}$: Binary variable equal to $1$ if project $p$ is active (runs this semester with at least one assigned student), and $0$ if it is not offered.
- $\rho \in \mathbb{R}_{\ge 0}$: Auxiliary variable bounding the worst assigned rank, linked by $\rho \ge r_{s,p}\,x_{s,p}\ \forall s \in S,\ p \in P$. It is used only in Strategy 1.

### 2.4 Hard Mathematical Constraints
Formulate all mandatory system constraints mathematically:

1. **Exact Allocation Constraint:**
   $$\sum_{p \in P} x_{s,p} = 1 \quad \forall s \in S$$
   *Explanation: Every student must receive exactly one project.*

2. **Project Headcount Capacity Bounds:**
   $$l_p\, y_p \le \sum_{s \in S} x_{s,p} \le u_p\, y_p \quad \forall p \in P$$
   *Explanation: An active project ($y_p = 1$) must respect its minimum and maximum quotas; an inactive project ($y_p = 0$) has no students.*

   **Project Activation Linking:**
   $$x_{s,p} \le y_p \quad \forall s \in S,\ \forall p \in P$$
   *Explanation: A student can only be assigned to a project that is active. Together with the bounds above, this means $y_p = 1$ if and only if at least one student is assigned to $p$ (given $l_p \ge 1$ for active projects).*

3. **Administrative Fixed Allocations (Locks):**
   $$x_{s^*, p^*} = 1 \quad \forall (s^*, p^*) \in F$$
   *Explanation: Pre-assigned pairs must be strictly enforced.*

4. **Mandatory Skill Qualification:**
   $$\sum_{s \in Q_{p,k}} x_{s,p} \ge y_p \quad \forall p \in P,\ \forall k \in K_p^{M}$$
   *Explanation: Every active project must have at least one assigned student who meets each of its mandatory skill requirements. Multiplying the right-hand side by $y_p$ means inactive projects impose no condition. If $Q_{p,k} = \emptyset$ for some mandatory $(p,k)$, project $p$ can never be active, which forces $y_p = 0$ (and the model is infeasible if a fixed assignment in $F$ locks a student to $p$).*

5. **Distinct Alternative Solutions (No-Good Integer Cuts):**
   $$\sum_{(s,p) \in A^{(i)}} x_{s,p} \le |S| - d \quad \forall A^{(i)} \in \mathcal{A}$$
   *Explanation: Every new solution must differ from each previously found allocation for at least $d$ students, where $d \ge 1$ is the minimum number of students that must receive a different project. The specification requires only $d = 1$ (at least one student differs); a larger $d$ yields more clearly distinct alternatives. If the model becomes infeasible after a cut is added, no further distinct alternatives exist and the engine reports this instead of repeating a solution.*

### 2.5 Optimization Objectives & Strategies
All three strategies are solved subject to the same constraints (constraints 1 to 5 of Section 2.4). Only the objective changes, so differences between solutions are caused by the objective alone.

- **Strategy 1: Preference-Oriented (Minimize Regret)**
  $$\max Z_{\text{pref}} = \sum_{s \in S}\sum_{p \in P} w^{\text{pref}}_{s,p}\,x_{s,p} \;-\; \mu\,\rho \;+\; \varepsilon \sum_{s \in S}\sum_{p \in P} \sigma_{s,p}\,x_{s,p}$$
  *Explanation: The first term is total Borda satisfaction: a better rank always scores more, and an unranked assignment scores $0$. The term $\mu\rho$ penalizes the worst assigned rank (an unranked assignment counts as rank $|P|+1$) and so limits individual regret. The last term only breaks ties in favor of better skill fit and, since $\varepsilon \le 1/(|S|+1)$, it can never override a difference in Borda satisfaction.*

- **Strategy 2: Skill-Fit-Oriented (Maximize Quality)**
  $$\max Z_{\text{skill}} = \sum_{s \in S}\sum_{p \in P} \sigma_{s,p}\,x_{s,p} \;+\; \varepsilon \sum_{s \in S}\sum_{p \in P} \tilde w_{s,p}\,x_{s,p}$$
  *Explanation: Maximizes the total skill-fit score, which is equivalent to maximizing $\bar\sigma$. The scores $\sigma_{s,p}$ are precomputed constants, so the objective is linear. Mandatory skills are enforced by constraint 4 of Section 2.4, so this objective only optimizes the non-mandatory requirements. Preference breaks ties.*

- **Strategy 3: Balanced Trade-Off (Compromise)**
  $$\max Z_{\text{balanced}} = \lambda \sum_{s \in S}\sum_{p \in P} \tilde w_{s,p}\,x_{s,p} \;+\; (1-\lambda) \sum_{s \in S}\sum_{p \in P} \sigma_{s,p}\,x_{s,p}$$
  *Explanation: A weighted sum of normalized preference satisfaction and skill fit, both on a $[0,1]$ scale per student. $\lambda = 1$ recovers Strategy 1 and $\lambda = 0$ recovers Strategy 2 (apart from the tie-breakers). A weighted sum can only reach supported Pareto-optimal points; this is discussed in Section 7.*

---

## 3. Evaluation Indicators & Analytical Metrics

Define the mathematical formulation for all evaluation metrics implemented in `app/engine/metrics.py`:

### 3.1 Feasibility Indicators
Each check re-verifies a hard constraint of Section 2.4 on the returned solution, with $n_p = \sum_{s \in S} x_{s,p}$:
- Allocation completeness: $\sum_{s \in S} \sum_{p \in P} x_{s,p} = |S|$
- Capacity compliance: $l_p \le n_p \le u_p$ for every project with $n_p > 0$
- Fixed lock adherence: $x_{s^*,p^*} = 1$ for every $(s^*, p^*) \in F$
- Mandatory requirement fulfillment count: number of pairs $(p, k)$ with $n_p > 0$, $k \in K_p^{M}$ and $\sum_{s \in Q_{p,k}} x_{s,p} = 0$ (must be $0$)

### 3.2 Efficiency Indicators
- **Mean Skill-Fit Score ($\bar{\sigma}$):**
  $$\bar{\sigma} = \frac{1}{|S|} \sum_{s \in S} \sum_{p \in P} \sigma_{s,p} \cdot x_{s,p}$$
- **Mean Preference Rank ($\bar{r}$):**
  $$\bar{r} = \frac{1}{|S|} \sum_{s \in S} \sum_{p \in P} r_{s,p} \cdot x_{s,p}$$

### 3.3 Fairness Indicators
*Section 6.3 of the specification mandates: rank distribution, unranked count, worst assigned rank, and ONE proposed and justified fairness indicator.*

1. **Rank Distribution:** Histogram vector $[c_1, c_2, \dots, c_{|P|}, c_{\text{unranked}}]$ where $c_k$ is the number of students assigned to their $k$-th choice.
2. **Unranked Allocation Count ($U$):** Count of students allocated outside their submitted preference list.
3. **Worst Assigned Rank ($r_{\max}$):**
   $$r_{\max} = \max_{(s,p) : x_{s,p}=1} r_{s,p}$$
4. **Team's Proposed Fairness Indicator (e.g., Gini Coefficient or Rank Variance):**
   *Provide the mathematical formula, justification, and interpretation:*
   $$G = \frac{\sum_{i=1}^n \sum_{j=1}^n |r_i - r_j|}{2 n \sum_{i=1}^n r_i}$$
   *The Gini coefficient measures how evenly preference outcomes are spread across the cohort, from 0 when every student gets the same rank to close to 1 when a few students do much better than the rest. It complements the mean rank and the worst rank, because two solutions can have the same mean while one gives everyone their second choice and the other splits students between first and third choices. Like the Jain's index used by Rezaeinia et al. (2022), it is bounded and does not depend on cohort size, but because it is relative it should always be read together with the mean rank.*

### 3.4 Capacity Utilization Metrics
- Per-project utilization percentage:
  $$\text{Util}_p = \frac{\sum_{s \in S} x_{s,p}}{u_p} \times 100\%$$
- Aggregate cohort capacity slack and tightness

---

## 4. Trade-Off Analysis & Solution Comparison

### 4.1 Comparative Delta Formulation
Explain how the system computes performance deltas between Solution A and Solution B:
$$\Delta \bar{\sigma} = \bar{\sigma}_B - \bar{\sigma}_A$$
$$\Delta \bar{r} = \bar{r}_B - \bar{r}_A$$
$$\Delta r_{\max} = r_{\max, B} - r_{\max, A}$$
$$\Delta G = G_B - G_A$$

### 4.2 Allocation Diff & Displaced Student Identification
Define how student re-allocations are classified:
- **Changed Assignments:** $\{(s, p_A, p_B) : x_{s, p_A}^{(A)} = 1 \land x_{s, p_B}^{(B)} = 1 \land p_A \ne p_B\}$
- **Worsened Students ($\Delta r_s > 0$):** Students whose preference rank worsened in Solution B.
- **Improved Students ($\Delta r_s < 0$):** Students whose preference rank improved in Solution B.

---

## 5. Transparent Recommendation Rules

*In accordance with Section 9 of the specification, recommendations must separate calculated evidence from advice across distinct policy priorities.*

### 5.1 Policy Priority 1: Student Preference Maximization
- **Quantitative Selection Criterion:** Recommend the Strategy 1 solution, which maximizes total Borda satisfaction and penalizes the worst assigned rank. Among its alternatives, prefer the fewest unranked students, then the lowest mean rank, then the lowest worst rank.
- **Calculated Evidence Reported:** Rank distribution, mean rank, worst rank, unranked count and Gini coefficient. Mean skill fit and unmet soft requirements are shown alongside as the cost to businesses.
- **Administrative Advice & Trade-Off Warning:** Use this when student satisfaction and perceived fairness matter most, for example when projects have few skill demands. Teams may be weaker, so compare their mean skill fit with Strategy 2 to see what businesses give up.

### 5.2 Policy Priority 2: Project Delivery & Technical Competence
- **Quantitative Selection Criterion:** Recommend the Strategy 2 solution, which maximizes total skill fit. Among its alternatives, prefer the highest mean skill fit, then the fewest unmet soft requirements.
- **Calculated Evidence Reported:** Mean skill fit, unmet soft requirements, mandatory-skill coverage and capacity utilization. Mean rank and unranked count are shown alongside as the cost to students.
- **Administrative Advice & Trade-Off Warning:** Use this when project delivery matters most, for example for demanding partner projects. Students may end up far from their preferences, so compare the unranked count and worst rank with Strategy 1.

### 5.3 Policy Priority 3: Balanced & Egalitarian Compromise
- **Quantitative Selection Criterion:** Recommend the Strategy 3 solution, which weights normalized preference and skill fit equally (λ = 0.5). Among its alternatives, prefer the lowest Gini coefficient.
- **Calculated Evidence Reported:** All indicators, plus the deltas against Strategies 1 and 2 from Section 4.1. These show how much each side gives up relative to its own best solution.
- **Administrative Advice & Trade-Off Warning:** Use this as the default when neither students nor businesses have clear priority. The result depends on λ and can only reach supported Pareto points, so it is a compromise rather than the best of both (see Section 7).

---

## 6. Assumptions, Boundary Conditions & Edge Cases

Document all operational assumptions:
1. **Student Submission Incompleteness:** An unranked project receives the penalty rank |P|+1 and a Borda score of 0 (Section 2.2), so it is never preferred over a ranked project.
2. **Ties in Preferences:** Students with identical preference lists are treated symmetrically, so the solver returns one of several equally good allocations and the others are surfaced as alternatives through the no-good cuts.
3. **Skill Levels:** A student with no declared level in a required skill scores 0 on that skill, and a project with no requirements gives every student a skill fit of 1 (Section 2.2).
4. **Feasibility Boundaries:** Since projects may be left inactive, the problem is infeasible when no set of projects can host all students within their minimum and maximum capacities, when the locks to a project exceed its maximum capacity, or when a student is locked to a project whose mandatory skill no student meets. These are necessary conditions checked before solving; the final proof of infeasibility is the solver reporting that no solution exists.

---

## 7. Limitations & Analytical Deficiencies

Critically reflect on the limitations of your analytical model:
1. **Computational Complexity:** Solve time for an integer program can grow quickly as |S| and |P| increase, but at course scale the solver typically finishes in seconds. If a run hits the 15-second solver time limit the returned solution may not be optimal, and every additional alternative requires a full re-solve.
2. **Linear Preference Assumptions:** The Borda score assumes the gap between a 1st and 2nd choice equals the gap between a 4th and 5th choice, which real student utilities need not follow. The weighted sum in Strategy 3 also depends on λ and can only reach supported Pareto-optimal points, so some good compromises between preference and skill fit cannot be found by it.
3. **Individual vs. Team Synergies:** Skill fit is scored per student and averaged, so a team in which one strong student covers a skill for the others can look weaker than it is. The model also does not capture diversity requirements such as gender, nationality or language.
4. **Static Allocation:** The assignment is made once and does not handle drop-outs or mid-semester changes, although re-running with current assignments fixed as locks gives a partial remedy.
5. **Tie-Breaking in Strategy 2:** Because skill-fit scores are fractional, the ε preference term is not a strict tie-breaker and can slightly override small differences in skill fit.
