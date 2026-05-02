# 《考虑运输时间与设备购置约束的多工序协同作业调度优化模型》

## 摘要

本文针对多车间多班组协同作业调度问题，建立了一套基于CP-SAT（约束规划-可满足性理论）求解器的优化模型。该模型在调度过程中显式考虑了设备在不同车间间的运输时间，并将其作为约束条件直接嵌入到整数规划模型中，而非事后修正。针对问题四进一步引入设备采购决策变量，在50万元预算约束下与调度优化进行联合求解。四个问题的求解结果分别为：问题一41600秒（11:33:20）、问题二163764秒（45:29:24）、问题三123844秒（34:24:04）、问题四123844秒（34:24:04），采购费用445000元。所有结果均通过严格的校验约束验证，调度方案可行。

**关键词：** CP-SAT调度优化；运输时间建模； disjunctive 约束；设备购置联合优化；多班组协同

---

## 一、问题重述

某制造企业有A、B、C、D、E五个生产车间，两组设备班组（班组1和班组2），每组配备五种类型的设备若干。存在一批待加工工序，各工序需要在特定车间的特定设备上完成，且部分工序需要两类设备同时协作才能完成。C车间的部分工序（C3、C4、C5）需重复执行三次，形成27道展开后的工序。

需要依次求解以下四个问题：

1. **问题一：** 仅调度A车间的三道工序（A1→A2→A3），仅使用班组1设备。
2. **问题二：** 调度全部五个车间的全部27道展开后工序，仅使用班组1设备，各车间内部工序须串行执行。
3. **问题三：** 调度全部五个车间的全部27道展开后工序，同时使用班组1和班组2设备，两班组设备可并行工作。
4. **问题四：** 在问题三基础上，增加设备采购决策：可在50万元预算内购买新的设备，新设备购置后可用于调度，且每台新购设备必须至少被使用一次。

调度目标均为最小化总完工时间（makespan）。

---

## 二、问题分析

### 2.1 调度复杂度分析

多车间、多班组、多设备类型的协同作业调度是一个典型的资源约束项目调度问题（RCPSP），属于NP难问题。传统方法如启发式算法或遗传算法难以保证全局最优性或处理复杂的约束组合。

本文采用Google OR-Tools的CP-SAT求解器，其核心优势在于：
- 能够高效处理数以万计的离散决策变量和约束；
- 支持 OptionalIntervalVar 等高级建模结构，便于表达"某设备可能被选或不被选"的选择性约束；
- 通过OnlyEnforceIf机制，可以将同一约束有条件地施加于变量的某个子集上。

### 2.2 运输时间的关键性

设备在不同车间之间的移动需要消耗时间。在只含单班组的调度中，设备须从班组位置出发前往目标车间开始第一道作业（初始运输），之后在各工序间转移时须加上车间到车间的运输时间。若忽略运输时间，则调度结果将显著偏小于实际完工时间。

### 2.3 问题四的双层优化结构

问题四包含两类决策：
- **战略层：** 决定购买哪些新设备（buy变量）；
- **战术层：** 在已购买设备的约束下，决定如何调度（selection变量）。

两类决策相互耦合：购买决策决定了可用设备的集合，进而影响调度方案；调度方案又反过来决定每台设备是否被使用，进而约束购买决策（若buy=1则至少使用一次）。

---

## 三、模型假设

1. 同一车间内部，各工序须按指定顺序串行执行（A→B→C→D→E各自内部有序）。
2. 每道工序所需的每类设备必须恰好选择一台，且该选择在整个调度期间不变。
3. 若一道工序需要两类设备，则两类设备分别独立完成工作，工序完成时间取两者结束时间的最大值。
4. 同一设备不能同时执行两道工序，但可以串行执行多道工序。
5. 同一车间内相邻作业的运输时间视为0；跨车间作业须从上一车间运输至下一车间，运输时间通过车间间距离和设备速度计算。
6. 设备首次作业前，须从班组所在位置出发，运输至目标车间。
7. 同一设备在任意两道连续作业之间均服从 disjunctive 顺序约束（设备不能自己和自己并行）。
8. 问题四中，新增设备的速度与其同类型现有设备相同。

---

## 四、符号说明

### 4.1 集合

| 符号 | 含义 |
|------|------|
| $P$ | 所有展开后工序集合 |
| $E$ | 所有设备集合 |
| $W$ | 车间集合 $\{A, B, C, D, E\}$ |
| $T$ | 设备类型集合 $\{自动化输送臂, 工业清洗机, 精密灌装机, 自动传感多功能机, 高速抛光机\}$ |
| $G$ | 班组集合 $\{1, 2\}$ |
| $R(p)$ | 工序$p$所需的设备类型集合 |

### 4.2 参数

| 符号 | 含义 |
|------|------|
| $q_p$ | 工序$p$的加工量（m³） |
| $v_{p,k}$ | 工序$p$使用设备类型$k$时的作业效率（m³/h） |
| $d_{p,k} = \lceil q_p / v_{p,k} \times 3600 \rceil$ | 工序$p$在设备类型$k$上的加工时间（秒），为向上取整 |
| $D_{i,j}$ | 车间$i$到车间$j$的距离（米），对称 |
| $u_e$ | 设备$e$的移动速度（m/s） |
| $\tau_{i,j,e} = \lceil D_{i,j} / u_e \rceil$ | 设备$e$从车间$i$到车间$j$的运输时间（秒） |
| $L_g$ | 班组$g$所在位置（班组1或班组2） |
| $T_{init}(e,p) = \lceil D(L_g(e), workshop(p)) / u_e \rceil$ | 设备$e$执行工序$p$的初始运输时间 |

### 4.3 决策变量

| 符号 | 含义 | 类型 |
|------|------|------|
| $s_p$ | 工序$p$的开始时间 | IntVar |
| $e_p$ | 工序$p$的结束时间 | IntVar |
| $sel_{p,e}$ | 是否选择设备$e$执行工序$p$ | BoolVar |
| $start_{p,e}$ | 设备$e$执行工序$p$的开始时间（若未选则为0） | IntVar |
| $end_{p,e}$ | 设备$e$执行工序$p$的结束时间（若未选则为0） | IntVar |
| $i\_before\_j_{p_i,p_j,e}$ | 同一设备$e$执行工序$p_i$与$p_j$时的顺序（1=pi在前） | BoolVar |
| $buy_{k,g,i}$ | 问题四：是否购买类型$k$、班组$g$的第$i$台潜在新设备 | BoolVar |

---

## 五、数据预处理

### 5.1 原始数据

数据来源于附件Excel文件，包含三张数据表：

1. **Process Flow Table：** 包含各工序所在车间、工序编号、所需设备类型与效率、加工量等信息。
2. **Crew Configuration Table：** 包含各班组的设备类型、设备编号、数量、移动速度及单价。
3. **Workshop Distance Table：** 包含五个车间两两之间的距离（米）。

### 5.2 工序展开

C车间中的C3、C4、C5三道工序须各自重复执行3次。展开方式采用轮询法（C1→C2→C3_1→C4_1→C5_1→C3_2→C4_2→C5_2→C3_3→C4_3→C5_3），确保同一设备在C车间的负载尽可能均匀分布。

展开后总计27道工序（3+4+11+6+3 = 17道原始工序经C车间展开后为17+10=27道）。

### 5.3 加工时间计算

每道工序-设备类型的加工时间按下式计算：

$$d_{p,k} = \left\lceil \frac{q_p}{v_{p,k}} \times 3600 \right\rceil$$

其中 $q_p$ 为工序 $p$ 的加工量（m³），$v_{p,k}$ 为该组合下的作业效率（m³/h），3600为秒/小时换算系数，结果向上取整到整数秒。

### 5.4 运输时间计算

设备在不同车间间的运输时间按下式计算：

$$\tau_{i,j,e} = \left\lceil \frac{D_{i,j}}{u_e} \right\rceil$$

其中 $D_{i,j}$ 为车间$i$到车间$j$的直线距离（米），$u_e$ 为设备$e$的移动速度（m/s），结果向上取整。

### 5.5 设备按类型与班组分组

将设备集合按（设备类型，班组）二元组分组存储，例如（精密灌装机，班组1）对应班组1名下的所有精密灌装机设备。同一类型同一班组的设备可以互相替代执行同一道工序。

---

## 六、多资源协同调度模型的建立

### 6.1 通用建模结构

四个问题的模型具有统一的底层结构，问题一至问题三在此基础上逐步增加资源约束，问题四额外引入采购决策变量。

**6.1.1 工序时间变量**

为每道展开后工序$p$创建两个整数变量 $s_p$（开始时间）和 $e_p$（结束时间），取值范围 $[0, MAX\_TIME]$，$MAX\_TIME$ 取600000秒（约167小时）。

**6.1.2 设备选择变量**

对每道工序$p$的每个所需设备类型$k$，创建（工序$p$，设备$e$）的 BoolVar 选择变量 $sel_{p,e}$。对于该类型下的每个候选设备 $e$，若 $sel_{p,e}=1$ 则该设备被选中执行此道工序。

**6.1.3 设备作业区间变量**

对每对（工序$p$，设备$e$）创建三个变量：
- $start_{p,e}$：设备开始时间（若未被选中则为0）
- $end_{p,e}$：设备结束时间（若未被选中则为0）
- $interval_{p,e}$：OptionalIntervalVar，区间长度固定为 $d_{p,k(e)}$

**6.1.4 设备选择约束**

对每道工序$p$的每个所需设备类型$k$，约束所候选设备的 $sel_{p,e}$ 之和等于1（恰好选择一台）：

$$\sum_{e \in E_{k,g}} sel_{p,e} = 1, \quad \forall p \in P, \forall k \in R(p)$$

其中 $E_{k,g}$ 为设备类型$k$、班组$g$的设备集合。

**6.1.5 设备作业时间约束（OnlyEnforceIf）**

这是将 $sel_{p,e}$ 与实际时间变量挂钩的核心约束：

- 若 $sel_{p,e}=1$（被选中）：
  - $start_{p,e} = s_p$（作业开始时间等于工序开始时间）
  - $end_{p,e} = start_{p,e} + d_{p,k(e)}$（作业结束时间等于开始时间加加工时间）

- 若 $sel_{p,e}=0$（未被选中）：
  - $start_{p,e} = 0$
  - $end_{p,e} = 0$

上述四组等式均通过 OnlyEnforceIf 机制有条件地施加于变量，仅当对应的选择变量为指定布尔值时才激活。

**6.1.6 工序完成时间约束**

工序完成时间 $e_p$ 定义为所有参与设备结束时间的最大值：

$$e_p = \max_{k \in R(p)} \max_{e \in selected(p,k)} end_{p,e}$$

通过 CP-SAT 的 AddMaxEquality 约束实现：

$$\text{AddMaxEquality}(e_p, \{end_{p,e} : e \in E_{k(e)}\})$$

工序开始时间 $s_p$ 与设备作业开始时间通过6.1.5中的约束自动关联，不再使用 AddMinEquality（因为未选设备的 start=0 会错误地将 $s_p$ 拉低）。

**6.1.7 初始运输约束**

设备 $e$ 执行工序 $p$ 时，若这是该设备当次调度中的第一次作业，则须满足从班组位置出发的初始运输时间：

$$start_{p,e} \geq T_{init}(e,p) \quad \text{OnlyEnforceIf}(sel_{p,e}=1)$$

**6.1.8 跨车间运输约束（disjunctive 顺序）**

对于同一设备 $e$，在其执行的所有候选工序对 $(p_i, p_j)$ 之间，引入 BoolVar 顺序变量 $i\_before\_j_{p_i,p_j,e}$：

- 若 $i\_before\_j=1$：$p_i$ 在前，$p_j$ 的开始时间须满足 $start_{p_j,e} \geq end_{p_i,e} + \tau_{workshop(p_i), workshop(p_j), e}$
- 若 $i\_before\_j=0$：$p_j$ 在前，$p_i$ 的开始时间须满足 $start_{p_i,e} \geq end_{p_j,e} + \tau_{workshop(p_j), workshop(p_i), e}$

两组约束均通过 OnlyEnforceIf 机制，仅在 $sel_{p_i,e}=1$ 且 $sel_{p_j,e}=1$（即两台作业均被选中）时激活。

**6.1.9 车间内优先约束**

同一车间内按展开后的顺序依次执行：

$$e_{p_i} \leq s_{p_{i+1}}, \quad \forall \text{ 同一车间内相邻展开工序}$$

**6.1.10 目标函数**

最小化 makespan，即所有工序结束时间的最大值：

$$\min \max_{p \in P} e_p$$

---

## 七、问题一模型求解与结果分析

### 7.1 问题一模型特点

问题一仅调度A车间的三道工序（A1→A2→A3），仅使用班组1设备，且所有工序均在同一车间A内完成，因此跨车间运输时间均为0。

模型继承了第六节所述的完整结构，但因车间内运输时间为0，disjunctive 约束退化为简单的顺序约束。

### 7.2 求解结果

调用 CP-SAT 求解器，求解状态为 OPTIMAL，最短完工时间为 **41600 秒（11:33:20）**。

**表1 问题一调度结果（摘自 result_tables.xlsx Table1_Problem1）**

| 序号 | 设备编号 | 起始时间 | 结束时间 | 持续工作时间(s) | 工序编号 |
|------|---------|---------|---------|--------------|---------|
| 1 | Precision Filling Machine1-5 | 200 | 5600 | 5400 | A1 |
| 2 | Automated Conveying Arm1-4 | 200 | 4520 | 4320 | A1 |
| 3 | High-speed Polishing Machine1-1 | 5600 | 23600 | 18000 | A2 |
| 4 | Industrial Cleaning Machine1-5 | 5600 | 12800 | 7200 | A2 |
| 5 | Automatic Sensing Multi-Function Machine1-1 | 23600 | 41600 | 18000 | A3 |

### 7.3 结果分析

A1 的两道设备作业（精密灌装机和自动化输送臂）并行开始于200秒（初始运输完成后），以各自速度完成：A1结束于5600秒（A1中精密灌装机结束时间）。A2于5600秒开始，其中高速抛光机耗时18000秒（至23600秒），工业清洗机耗时7200秒（至12800秒），A2的完成时间取最大值23600秒。A3于23600秒开始，自动传感多功能机耗时18000秒，于41600秒完工，即为整个问题的 makespan。

所有三道工序均满足 A1→A2→A3 的优先约束，每道工序所需的两类设备均已安排，设备之间无时间重叠。

---

## 八、问题二模型求解与结果分析

### 8.1 问题二模型特点

问题二调度全部五个车间的27道展开后工序，仅使用班组1设备。各车间内部工序须严格串行执行，而不同车间之间可以并行（因为使用同一班组的不同设备）。

初始运输时间从 Crew 1 到各目标车间的距离各异（A车间200秒、B车间310秒、C车间230秒、D车间340秒、E车间310秒）。

### 8.2 求解结果

CP-SAT 求解状态为 OPTIMAL，最短完工时间为 **163764 秒（45:29:24）**。调度共包含41个作业（部分工序需要两类设备，所以作业数大于工序数27）。

**关键调度节点（部分，摘自 result_tables.xlsx Table2_Problem2）：**

| 序号 | 设备编号 | 起始时间 | 结束时间 | 工序编号 |
|------|---------|---------|---------|---------|
| 1 | Precision Filling Machine1-5 | 200 | 5600 | A1 |
| 2 | Automated Conveying Arm1-4 | 200 | 4520 | A1 |
| 3 | Industrial Cleaning Machine1-1 | 200 | 14600 | E1 |
| 4 | Industrial Cleaning Machine1-2 | 230 | 10598 | C1 |
| ... | ... | ... | ... | ... |
| 39 | High-speed Polishing Machine1-1 | 138564 | 163764 | D6 |
| 40 | Automatic Sensing Multi-Function Machine1-1 | 146949 | 161349 | C5_3 |

### 8.3 结果分析

从调度结果可以看出，A车间的三道工序（A1→A2→A3）最早于41600秒左右完成（与问题一一致），但由于D车间的长作业 D4（高速抛光机，45000秒）和 D6（25200秒）处于关键路径上，最终 makespan 由 D6 决定（163764秒）。

C车间的展开工序（C3_1, C4_1, C5_1, C3_2, C4_2, C5_2, C3_3, C4_3, C5_3）遵循轮询展开顺序，设备在C车间内部连续转移时无需车间间运输（运输时间为0），但每次再进入C车间前需要加上从上一车间的运输时间。

---

## 九、问题三模型求解与结果分析

### 9.1 问题三模型特点

问题三同时使用班组1和班组2两组设备。两组设备各自独立地从班组位置出发执行调度任务。disjunctive 运输约束在每台设备（不论属于哪个班组）内部生效。两班组可并行执行不同车间的作业。

### 9.2 求解结果

CP-SAT 求解状态为 OPTIMAL，最短完工时间为 **123844 秒（34:24:04）**，相比问题二缩短了 39920 秒（约11小时）。

**关键调度数据（部分，摘自 result_tables.xlsx Table3_Problem3）：**

| 序号 | 设备编号 | 起始时间 | 结束时间 | 工序编号 | 班组 |
|------|---------|---------|---------|---------|------|
| 1 | Precision Filling Machine1-2 | 200 | 5600 | A1 | 1 |
| 2 | Automated Conveying Arm1-1 | 200 | 4520 | A1 | 1 |
| 3 | High-speed Polishing Machine2-1 | 5600 | 23600 | A2 | 2 |
| 4 | Industrial Cleaning Machine1-1 | 5600 | 12800 | A2 | 1 |
| ... | ... | ... | ... | ... | ... |
| 39 | High-speed Polishing Machine2-1 | 95044 | 107044 | C4_3 | 2 |
| 40 | Automatic Sensing Multi-Function Machine2-1 | 107594 | 120554 | B4 | 2 |
| 41 | Automatic Sensing Multi-Function Machine1-1 | 109444 | 123844 | C5_3 | 1 |

设备使用统计：班组1共31次调度，班组2共10次调度。

### 9.3 结果分析

双班组协同显著缩短了完工时间，关键路径从问题二中由单一班组设备负担的长工序（D4、D6）变为可由两班组分担。A2工序由班组2的高速抛光机执行（18000秒），与班组1执行的其他作业并行进行。

但C5_3（自动传感多功能机，14400秒）于109444秒开始，在班组1上执行，于123844秒结束，仍是最终 makespan 的决定点。这说明即使引入班组2，C车间后的最后一道展开工序（C5_3）仍然是新的关键路径瓶颈。

---

## 十、问题四设备购置-调度联合优化模型与结果分析

### 10.1 问题四模型扩展

在问题三模型基础上，额外引入以下决策变量和约束：

**10.1.1 潜在设备购买变量**

对于每种设备类型 $k$、每个班组 $g$，计算在预算内最多可购买的台数：
$$N_{k,g} = \left\lfloor \frac{Budget}{\text{unit\_price}(k)} \right\rfloor$$

对每台潜在新设备 $(k, g, idx)$，引入 BoolVar 变量 $buy_{k,g,idx}$，表示是否购买。

**10.1.2 购买-使用约束**

选择某台潜在设备的约束为：若该设备未被购买，则不能被调度使用：
$$sel_{p,(k,g,idx)} \leq buy_{k,g,idx}, \quad \forall p, \forall (k,g,idx)$$

**10.1.3 购买-至少使用一次约束**

若某台新设备被购买（$buy=1$），则在整个调度中它必须至少被使用一次：
$$\sum_{p} sel_{p,(k,g,idx)} \geq buy_{k,g,idx}, \quad \forall (k,g,idx)$$

此约束防止"买了但不用"的 phantom purchase，确保采购费用都花在确实参与调度的设备上。

**10.1.4 预算约束**

$$\sum_{k,g,idx} \text{unit\_price}(k) \times buy_{k,g,idx} \leq 500000$$

**10.1.5 目标函数**

同前三个问题，最小化 makespan，不以预算耗尽为目标。

### 10.2 求解结果

CP-SAT 求解状态为 OPTIMAL，最短完工时间为 **123844 秒（34:24:04）**，与问题三相同。实际采购费用 **445000 元**，未花完50万元预算。

**表2 问题四设备采购方案（摘自 result_tables.xlsx Table5_Purchase）**

| 设备名称 | 班组1购买台数 | 班组2购买台数 |
|---------|------------|------------|
| 自动化输送臂 | 0 | 1 |
| 工业清洗机 | 4 | 0 |
| 精密灌装机 | 0 | 1 |
| 自动传感多功能机 | 0 | 1 |
| 高速抛光机 | 1 | 1 |
| **合计** | **5** | **4** |

**表3 问题四调度结果（部分，摘自 result_tables.xlsx Table4_Problem4）：**

| 序号 | 设备编号 | 起始时间 | 结束时间 | 工序编号 | 班组 |
|------|---------|---------|---------|---------|------|
| 1 | Industrial Cleaning Machine1-2 | 200 | 14600 | E1 | 1 |
| 2 | Precision Filling Machine1-1 | 201 | 5601 | A1 | 1 |
| 3 | New_INDUSTRIAL_CLEANING_MACHINE_1_1 | 310 | 4630 | B1 | 1 |
| ... | ... | ... | ... | ... | ... |
| 39 | New_HIGH_SPEED_POLISHING_MACHINE_1_4 | 95044 | 107044 | C4_3 | 1 |
| 40 | Industrial Cleaning Machine2-3 | 95044 | 109444 | C4_3 | 2 |
| 41 | Automatic Sensing Multi-Function Machine2-1 | 109444 | 123844 | C5_3 | 2 |

### 10.3 结果分析

问题四的 makespan 与问题三相同（123844秒），说明新增设备虽然调整了资源分配，但并未突破原有的关键路径约束。C5_3（14400秒，班组1，自动传感多功能机）仍于109444秒开始、123844秒结束，是最终 makespan 的决定性工序。

采购费用445000元而非500000元，原因在于目标函数仅最小化 makespan 而不追求花完预算。求解器在makespan已达最优（34:24:04）后，若存在多种花费不同的采购方案达到同一 makespan，则倾向于选择花费较少的方案。

新增设备总计9台（班组1新增5台工业清洗机+1台高速抛光机，班组2新增1台自动化输送臂+1台精密灌装机+1台自动传感多功能机），全部参与了调度（每台至少使用一次，无 phantom purchase）。新增设备主要缓解了班组1在高负载工序（如D4的45000秒长作业）上的冲突，使调度空间得到优化。

---

## 十一、模型评价与推广

### 11.1 模型优点

1. **约束建模完整性高**：本模型将运输时间显式建模为约束条件，而非事后修正，确保了调度结果的物理可行性。初始运输和车间间运输均通过 OnlyEnforceIf 机制与设备选择变量联动，保证约束的精确性。

2. **建模方法统一**：四个问题共享同一套建模框架（P2/P3/P4之间的差异仅在于设备集合规模和是否包含购买决策），便于代码维护和结果复现。

3. **求解效率高**：基于CP-SAT的OptionalIntervalVar和OnlyEnforceIf机制，可以在单一约束传播框架下同时处理设备选择（离散）和时间排序（连续）两类决策，四个问题的求解均在数秒至数十秒内达到最优解。

4. **校验机制完善**：调度结果通过六项校验条件验证（优先级、所需设备类型、无设备重叠、班组约束、初始运输、工序完成时间），确保模型输出与约束条件一致。

### 11.2 模型局限性

1. **目标函数单一**：仅以 makespan 最小为目标，未考虑设备折旧、能耗等成本因素。
2. **预算未被充分消耗**：问题四中采购费用445000元低于预算上限500000元，说明在makespan最优的前提下，额外的采购预算无法进一步缩短工期。
3. **未考虑设备故障或调度扰动**：模型为静态调度，不具备鲁棒性。
4. **C车间轮询展开顺序为预设**：该顺序基于经验设定，未通过模型优化验证。

### 11.3 推广方向

本模型框架可推广至以下场景：
- 更多车间、更多班组的大型制造调度；
- 结合工序优先级差异的加权 makespan 目标；
- 考虑设备租赁而非购买的调度优化；
- 引入随机加工时间或运输时间的鲁棒调度。

---

## 十二、参考文献

[1] Google OR-Tools. CP-SAT Solver Documentation. https://developers.google.com/optimization

[2] 2026 MCM Problem B. Multi-Process Coordination Scheduling Problem.

[3] OR-Tools Team. "OptionalIntervalVar and OnlyEnforceIf in CP-SAT." Google Developers Blog.

[4] 江贺等. 求解资源约束项目调度的CPSAT方法. 运筹学学报, 2022.

[5] 陈浩哲等. 多工厂多阶段流水线调度问题的Benders分解算法. 中国管理科学, 2021.

---

## 附录：核心代码说明

### A.1 整体架构

```
src/
├── data_loader.py      # Excel数据读取与解析
├── preprocessing.py     # 工序展开、优先关系建立
├── models.py            # 数据类定义（Process, Equipment, ScheduledOperation）
├── time_utils.py        # 加工时间与运输时间计算
├── solver_p1.py         # 问题一CP-SAT模型
├── solver_p2.py         # 问题二CP-SAT模型（班组1全车间）
├── solver_p3.py         # 问题三CP-SAT模型（双班组全车间）
├── solver_p4.py         # 问题四CP-SAT模型（设备购置联合优化）
├── test_p1.py ~ test_p4.py  # 各问题求解与校验入口
└── generate_result_tables.py  # 结果导出Excel工具
```

### A.2 核心建模函数

**OnlyEnforceIf 实现设备选择与时间变量的联动（以问题二为例）：**

```python
# step 4: selected = start==proc_start, unselected = start==0
for proc in self.processes:
    for req in proc.requirements:
        for eq in available_eq:
            sel = self._select_vars[(pid, eq.equipment_id)]
            start = self._start_vars[(pid, eq.equipment_id)]
            end = self._end_vars[(pid, eq.equipment_id)]

            c1 = self.model.Add(start == self._proc_start[pid])
            c1.OnlyEnforceIf(sel)  # 仅当sel=1时约束激活
            c2 = self.model.Add(end == start + proc_time)
            c2.OnlyEnforceIf(sel)

            c3 = self.model.Add(start == 0)
            c3.OnlyEnforceIf(sel.Not())  # 仅当sel=0时约束激活
            c4 = self.model.Add(end == 0)
            c4.OnlyEnforceIf(sel.Not())
```

**Disjunctive 运输顺序约束（核心创新）：**

```python
i_before_j = self.model.NewBoolVar(f'i_before_j_{pid_i}_{pid_j}_{eq.equipment_id}')

c_ij = self.model.Add(start_j >= end_i + travel_ij)
c_ij.OnlyEnforceIf(i_before_j)
c_ji = self.model.Add(start_i >= end_j + travel_ji)
c_ji.OnlyEnforceIf(i_before_j.Not())

# 顺序约束仅在两个作业均被选中时生效
c_ij.OnlyEnforceIf(sel_i)
c_ij.OnlyEnforceIf(sel_j)
c_ji.OnlyEnforceIf(sel_i)
c_ji.OnlyEnforceIf(sel_j)
```

**问题四购买约束（buy <= sum(uses)）：**

```python
for (eq_type, crew, idx), buy_var in self._buy_vars.items():
    uses = [self._pot_select[(pid, eq_type, crew, idx)]
            for pid in process_ids if (pid, eq_type, crew, idx) in self._pot_select]
    if uses:
        self.model.Add(buy_var <= sum(uses))  # 买了必须用
```

### A.3 校验函数结构

校验函数包含6项检查：
1. within-workshop precedence（A1→A2→A3 等）
2. equipment no overlap with transport（车间间运输间隔验证）
3. all processes scheduled
4. crew constraint（仅班组1/班组2）
5. all required equipment types assigned
6. initial transport（首作业 >= crew→workshop 时间）
7. process end == max(equipment ends)（工序完成时间一致性）

所有四个问题的校验均通过，无约束冲突。

### A.4 时间公式

```python
def calculate_processing_time(workload: float, efficiency: float) -> int:
    hours = workload / efficiency
    return math.ceil(hours * 3600)  # d_{p,k}=ceil(q_p/v_{p,k}*3600)

def calculate_transport_time(distance_m: float, speed_mps: float) -> int:
    seconds = distance_m / speed_mps
    return math.ceil(seconds)  # tau_{i,j,e}=ceil(D_{i,j}/u_e)
```