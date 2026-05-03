# 五一数学建模竞赛

**题目：考虑运输时间与设备购置约束的多工序协同作业调度优化模型**

**关键词：** CP-SAT调度优化；运输时间建模；Disjunctive约束；设备购置联合优化；多班组协同

---

**摘要**

对于问题一，本文仅调度A车间的三道工序（A1→A2→A3），仅使用班组1设备，采用CP-SAT求解器建模并求解，最短完工时间为41600秒（11:33:20）。对于问题二，本文调度全部五个车间的27道展开后工序，仍仅使用班组1设备，最短完工时间为163764秒（45:29:24）。对于问题三，本文同时使用班组1和班组2两组设备，形成双班组并行协同调度，最短完工时间为123844秒（34:24:04），相比问题二缩短约11小时。对于问题四，本文在问题三基础上引入设备采购决策，在50万元预算约束下联合优化调度与采购方案，实际采购费用445000元（9台新设备），最短完工时间仍为123844秒（34:24:04）。所有结果均通过六项校验约束验证，调度方案可行。

---

# 一、问题重述

某制造企业有A、B、C、D、E五个生产车间，两组设备班组（班组1和班组2），每组配备五种类型的设备若干。存在一批待加工工序，各工序需要在特定车间的特定设备上完成，且部分工序需要两类设备同时协作才能完成。C车间的部分工序（C3、C4、C5）需各自重复执行三次，形成27道展开后的工序。

原始工序总计21道（A=3、B=4、C=5、D=6、E=3），其中C3、C4、C5各展开为3道，总工序数为21+6=27道。

需要依次求解以下四个问题：

1. **问题一：** 仅调度A车间的三道工序（A1→A2→A3），仅使用班组1设备。

2. **问题二：** 调度全部五个车间的全部27道展开后工序，仅使用班组1设备，各车间内部工序须串行执行。

3. **问题三：** 调度全部五个车间的全部27道展开后工序，同时使用班组1和班组2设备，两班组设备可并行工作。

4. **问题四：** 在问题三基础上，增加设备采购决策：可在50万元预算内购买新设备，新设备购置后可用于调度，且每台新购设备必须至少被使用一次。

调度目标均为最小化总完工时间（makespan）。

---

# 二、模型假设

1. 同一车间内部，各工序须按指定顺序串行执行。
2. 每道工序所需的每类设备必须恰好选择一台。
3. 若一道工序需要两类设备，则两类设备分别独立完成工作，工序完成时间取两者结束时间的最大值。
4. 同一设备不能同时执行两道工序，但可串行执行多道工序。
5. 同一车间内相邻作业的运输时间视为0；跨车间作业须加上车间间运输时间。
6. 设备首次作业前，须从班组所在位置出发运输至目标车间。
7. 同一设备在任意两道连续作业之间均服从Disjunctive顺序约束。
8. 问题四中，新增设备的速度与其同类型现有设备相同。

---

# 三、符号说明

**表1 符号说明表**

| 序号 | 符号 | 含义 |
|------|------|------|
| 1 | P | 所有展开后工序集合，|P|=27 |
| 2 | E | 所有设备集合 |
| 3 | W | 车间集合，W={A,B,C,D,E} |
| 4 | K | 五种设备类型集合 |
| 5 | G | 班组集合，G={1,2} |
| 6 | R(p) | 工序p所需的设备类型集合 |
| 7 | q_p | 工序p的加工量（m³） |
| 8 | v_{p,k} | 工序p使用设备类型k时的作业效率（m³/h） |
| 9 | d_{p,k} | 工序p在设备类型k上的加工时间（秒），d_{p,k}=ceil(q_p/v_{p,k}×3600) |
| 10 | D_{i,j} | 车间i到车间j的距离（米），D_{i,j}=D_{j,i} |
| 11 | u_e | 设备e的移动速度（m/s） |
| 12 | tau_{i,j,e} | 设备e从车间i到车间j的运输时间（秒），tau_{i,j,e}=ceil(D_{i,j}/u_e) |
| 13 | s_p | 工序p的开始时间 |
| 14 | C_p | 工序p的完成时间（C表示Completion） |
| 15 | sel_{p,e} | 是否选择设备e执行工序p（1=是，0=否） |
| 16 | start_{p,e} | 设备e执行工序p的开始时间（若未选则为0） |
| 17 | end_{p,e} | 设备e执行工序p的结束时间（若未选则为0） |
| 18 | buy_{k,g,i} | 是否购买类型k、班组g的第i台潜在新设备（1=是，0=否） |

---

# 四、问题分析

## 4.1 调度复杂度

多车间、多班组、多设备类型的协同作业调度是典型的资源约束项目调度问题（RCPSP），属于NP难问题。传统启发式算法难以保证全局最优性。

本文采用Google OR-Tools的CP-SAT求解器，支持OptionalIntervalVar等高级建模结构，通过OnlyEnforceIf机制将设备选择与时间约束联动处理。

## 4.2 运输时间的关键性

设备在不同车间间移动须消耗时间。若忽略运输时间，则调度结果将显著偏小于实际完工时间。本模型将初始运输（班组→首车间）和车间间运输（跨车间作业）均作为硬约束嵌入模型。

## 4.3 问题四的双层优化结构

问题四包含两类决策：战略层（购买哪些设备）和战术层（如何调度），通过约束"buy=1则至少使用一次"实现双向耦合，防止phantom purchase（phantom purchase指购买了但从未使用的设备）。

---

# 五、数据预处理

## 5.1 数据来源

数据来源于附件Excel文件，包含三张数据表：Process Flow Table（工序信息）、Crew Configuration Table（设备配置）、Workshop Distance Table（车间距离）。

## 5.2 工序展开

C车间中的C3、C4、C5三道工序须各自重复执行3次。展开方式采用轮询法（C1→C2→C3_1→C4_1→C5_1→C3_2→C4_2→C5_2→C3_3→C4_3→C5_3），确保同一设备在C车间的负载尽可能均匀分布。

展开后总计27道工序：原始21道工序中，C3、C4、C5各展开为3道，共增加6道，21+6=27道。

## 5.3 加工时间计算

$$d_{p,k} = \left\lceil \frac{q_p}{v_{p,k}} \times 3600 \right\rceil$$

其中q_p为工序p的加工量（m³），v_{p,k}为该组合下的作业效率（m³/h），3600为秒/小时换算系数，结果向上取整至整数秒。

## 5.4 运输时间计算

$$\tau_{i,j,e} = \left\lceil \frac{D_{i,j}}{u_e} \right\rceil$$

其中D_{i,j}为车间i到车间j的距离（米），u_e为设备e的移动速度（m/s），结果向上取整。

---

# 六、多资源协同调度模型的建立

## 6.1 设备选择约束

对每道工序p的每个所需设备类型k，约束候选设备的sel_{p,e}之和等于1：

$$\sum_{e \in E_{k,g}} sel_{p,e} = 1, \quad \forall p \in P, \forall k \in R(p)$$

其中E_{k,g}表示班组g中类型为k的设备集合。该约束保证每道工序的每类设备恰好选择一台。

## 6.2 设备作业时间约束（OnlyEnforceIf）

若sel_{p,e}=1（被选中）：start_{p,e} = s_p, end_{p,e} = start_{p,e} + d_{p,k(e)}

若sel_{p,e}=0（未被选中）：start_{p,e} = 0, end_{p,e} = 0

上述四组等式均通过OnlyEnforceIf机制有条件地施加——当sel=1时激活前者，当sel=0时激活后者。

## 6.3 工序完成时间约束

$$C_p = \max_{k \in R(p)} \max_{e \in selected(p,k)} end_{p,e}$$

即工序完成时间等于其所有参与设备结束时间的最大值，通过CP-SAT的AddMaxEquality约束实现。

## 6.4 初始运输约束

$$start_{p,e} \geq T_{init}(e,p) \quad OnlyEnforceIf(sel_{p,e}=1)$$

其中T_{init}(e,p)为设备e从班组位置运输至工序p所在车间的初始运输时间，仅当该设备被选中时约束生效。

## 6.5 跨车间运输约束（Disjunctive顺序）

引入BoolVar顺序变量i_before_j_{p_i,p_j,e}，表示同一设备e执行工序p_i与p_j时的顺序：

若i_before_j=1（p_i在前）：start_{p_j,e} >= end_{p_i,e} + tau_{workshop(p_i),workshop(p_j),e}

若i_before_j=0（p_j在前）：start_{p_i,e} >= end_{p_j,e} + tau_{workshop(p_j),workshop(p_i),e}

两组约束均通过OnlyEnforceIf机制，仅在两道作业均被选中时激活。

## 6.6 车间内优先约束

$$C_{p_i} \leq s_{p_{i+1}}, \quad \forall \text{同一车间内相邻展开工序}$$

即同一车间内相邻展开工序须严格串行执行。

## 6.7 目标函数

$$\min T, \quad T = \max_{p \in P} C_p$$

即最小化总完工时间makespan。

---

# 七、问题一模型求解与结果分析

## 7.1 模型特点

问题一仅调度A车间的三道工序（A1→A2→A3），仅使用班组1设备，所有工序均在同一车间A内完成，跨车间运输时间均为0。模型继承第六章所述的完整结构。

## 7.2 求解结果

CP-SAT求解状态为OPTIMAL，最短完工时间为**41600秒（11:33:20）**。

**表2 问题一调度结果（摘自result_tables.xlsx Table1_Problem1）**

| 序号 | 设备编号 | 起始时间 | 结束时间 | 持续工作时间(s) | 工序编号 |
|------|---------|----------|----------|----------------|---------|
| 1 | Precision Filling Machine1-5 | 00:03:20 | 01:33:20 | 5400 | A1 |
| 2 | Automated Conveying Arm1-4 | 00:03:20 | 01:15:20 | 4320 | A1 |
| 3 | High-speed Polishing Machine1-1 | 01:33:20 | 06:33:20 | 18000 | A2 |
| 4 | Industrial Cleaning Machine1-5 | 01:33:20 | 03:33:20 | 7200 | A2 |
| 5 | Automatic Sensing Multi-Function Machine1-1 | 06:33:20 | 11:33:20 | 18000 | A3 |

## 7.3 结果分析

A1的两道设备作业（精密灌装机和自动化输送臂）并行开始于200秒（00:03:20），A1完成于5600秒（01:33:20）。A2于5600秒开始，高速抛光机耗时18000秒（至23600秒，即06:33:20），工业清洗机耗时7200秒（至12800秒，即03:33:20），A2完成时间取最大值23600秒。A3于23600秒开始，自动传感多功能机耗时18000秒，于41600秒（11:33:20）完工，即为makespan。

---

# 八、问题二模型求解与结果分析

## 8.1 模型特点

问题二调度全部五个车间的27道展开后工序，仅使用班组1设备。各车间内部工序须严格串行执行，不同车间之间可以并行（使用同一班组的不同设备）。初始运输时间从Crew 1到各目标车间的距离各异（A车间200秒、B车间310秒、C车间230秒、D车间340秒、E车间310秒）。

## 8.2 求解结果

CP-SAT求解状态为OPTIMAL，最短完工时间为**163764秒（45:29:24）**，调度共包含41个作业（部分工序需要两类设备，所以作业数大于工序数）。

**表3 问题二调度结果（摘自result_tables.xlsx Table2_Problem2）**

| 序号 | 设备编号 | 起始时间 | 结束时间 | 持续工作时间(s) | 工序编号 |
|------|---------|----------|----------|----------------|---------|
| 1 | Precision Filling Machine1-5 | 00:03:20 | 01:33:20 | 5400 | A1 |
| 2 | Automated Conveying Arm1-4 | 00:03:20 | 01:15:20 | 4320 | A1 |
| 3 | Industrial Cleaning Machine1-1 | 00:03:20 | 04:03:20 | 14400 | E1 |
| 4 | Industrial Cleaning Machine1-2 | 00:03:50 | 02:56:38 | 10368 | C1 |
| 5 | Automated Conveying Arm1-1 | 00:03:50 | 02:56:38 | 10368 | C1 |
| ... | ... | ... | ... | ... | ... |
| 39 | High-speed Polishing Machine1-1 | 38:29:24 | 45:29:24 | 25200 | D6 |
| 40 | Automatic Sensing Multi-Function Machine1-1 | 40:49:09 | 44:49:09 | 14400 | C5_3 |

## 8.3 结果分析

A车间的三道工序（A1→A2→A3）最早于41600秒（11:33:20）左右完成（与问题一一致），但由于D车间的长作业D4（高速抛光机，45000秒）和D6（25200秒）处于关键路径上，最终makespan由D6决定（163764秒，即45:29:24）。

---

# 九、问题三模型求解与结果分析

## 9.1 模型特点

问题三同时使用班组1和班组2两组设备。两组设备各自独立地从班组位置出发执行调度任务。Disjunctive运输约束在每台设备（不论属于哪个班组）内部生效。两班组可并行执行不同车间的作业。

## 9.2 求解结果

CP-SAT求解状态为OPTIMAL，最短完工时间为**123844秒（34:24:04）**，相比问题二缩短了39920秒（约11小时）。

**表4 问题三调度结果（摘自result_tables.xlsx Table3_Problem3）**

| 序号 | 设备编号 | 起始时间 | 结束时间 | 持续工作时间(s) | 工序编号 | 班组 |
|------|---------|----------|----------|----------------|---------|------|
| 1 | Precision Filling Machine1-2 | 00:03:20 | 01:33:20 | 5400 | A1 | 1 |
| 2 | Automated Conveying Arm1-1 | 00:03:20 | 01:15:20 | 4320 | A1 | 1 |
| 3 | High-speed Polishing Machine2-1 | 01:33:20 | 06:33:20 | 18000 | A2 | 2 |
| 4 | Industrial Cleaning Machine1-1 | 01:33:20 | 03:33:20 | 7200 | A2 | 1 |
| ... | ... | ... | ... | ... | ... | ... |
| 39 | High-speed Polishing Machine2-1 | 26:23:44 | 29:44:44 | 10800 | B4 | 2 |
| 40 | Automatic Sensing Multi-Function Machine2-1 | 29:53:14 | 33:28:44 | 12960 | B4 | 2 |
| 41 | Automatic Sensing Multi-Function Machine1-1 | 30:24:04 | 34:24:04 | 14400 | C5_3 | 1 |

设备使用统计：班组1共33次调度，班组2共8次调度。

## 9.3 结果分析

双班组协同显著缩短了完工时间。A2工序由班组2的高速抛光机执行（18000秒），与班组1执行的其他作业并行进行。但C5_3（自动传感多功能机，14400秒）仍于109444秒（30:24:04）开始，在班组1上执行，于123844秒（34:24:04）结束，是最终makespan的决定点。

---

# 十、问题四设备购置-调度联合优化模型与结果分析

## 10.1 问题四模型扩展

在问题三模型基础上，额外引入以下决策变量和约束。

**潜在设备购买变量：** 对于每种设备类型k、每个班组g，计算在预算内最多可购买的台数：

$$N_{k,g} = \left\lfloor \frac{500000}{unit_price(k)} \right\rfloor$$

对每台潜在新设备(k,g,idx)，引入BoolVar变量buy_{k,g,idx}。

**购买-使用约束：**

$$sel_{p,(k,g,idx)} \leq buy_{k,g,idx}, \quad \forall p, \forall (k,g,idx)$$

即所购设备必须被使用，防止phantom purchase。

**购买-至少使用一次约束（防止phantom purchase）：**

$$\sum_{p} sel_{p,(k,g,idx)} \geq buy_{k,g,idx}, \quad \forall (k,g,idx)$$

即只有被使用的设备才被视为已购买，保证每台购置设备至少被调度一次。

**预算约束：**

$$\sum_{k,g,idx} unit_price(k) \times buy_{k,g,idx} \leq 500000$$

所有采购总费用不得超过预算上限。

**目标函数：** 同前三个问题，最小化makespan。

## 10.2 求解结果

CP-SAT求解状态为OPTIMAL，最短完工时间为**123844秒（34:24:04）**，与问题三相同。预算上限为500000元，实际采购费用**445000元**，未花完预算是因为目标函数为最小化makespan而非预算使用率最大化。

**表5 问题四调度结果（部分，摘自result_tables.xlsx Table4_Problem4）**

| 序号 | 设备编号 | 起始时间 | 结束时间 | 持续工作时间(s) | 工序编号 | 班组 |
|------|---------|----------|----------|----------------|---------|------|
| 1 | Industrial Cleaning Machine1-2 | 00:03:20 | 04:03:20 | 14400 | E1 | 1 |
| 2 | Precision Filling Machine1-1 | 00:03:21 | 01:33:21 | 5400 | A1 | 1 |
| 3 | Automated Conveying Arm1-3 | 00:03:21 | 01:15:21 | 4320 | A1 | 1 |
| ... | ... | ... | ... | ... | ... | ... |
| 39 | New_HIGH_SPEED_POLISHING_MACHINE_2_3 | 25:17:05 | 32:17:05 | 25200 | D6 | 2 |
| 40 | New_INDUSTRIAL_CLEANING_MACHINE_2_4 | 26:23:44 | 30:23:44 | 14400 | C4_3 | 2 |
| 41 | New_AUTOMATIC_SENSING_MULTI_FUNCTION_MACHINE_1_5 | 30:24:04 | 34:24:04 | 14400 | C5_3 | 1 |

**表6 问题四设备采购方案（摘自result_tables.xlsx Table5_Purchase）**

| 设备名称 | 班组1购买台数 | 班组2购买台数 |
|---------|------------|------------|
| 自动化输送臂 | 1 | 1 |
| 工业清洗机 | 2 | 1 |
| 精密灌装机 | 0 | 1 |
| 自动传感多功能机 | 1 | 1 |
| 高速抛光机 | 0 | 1 |
| **合计** | **4** | **5** |

新增设备共9台，全部参与调度，无phantom purchase。

## 10.3 结果分析

问题四的makespan与问题三相同（123844秒），说明新增设备虽调整了资源分配，但未突破原有的关键路径约束。最终makespan由C5_3决定，C5_3由班组1的New_AUTOMATIC_SENSING_MULTI_FUNCTION_MACHINE_1_5执行，开始时间109444秒（30:24:04），结束时间123844秒（34:24:04）。

采购费用445000元而非500000元，原因在于目标函数仅最小化makespan而不追求花完预算——当makespan已达最优（34:24:04）后，存在多种花费不同的采购方案，求解器倾向于选择花费较少的方案。

班组1新增4台设备（含工业清洗机2台、自动传感多功能机1台、自动化输送臂1台），班组2新增5台设备（含工业清洗机1台、精密灌装机1台、自动化输送臂1台、自动传感多功能机1台、高速抛光机1台），说明两班组的资源瓶颈均较为突出。

---

# 十一、模型评价与推广

## 11.1 模型优点

1. **约束建模完整性高：** 运输时间显式建模为硬约束，初始运输和车间间运输均通过OnlyEnforceIf机制与设备选择变量联动。

2. **建模框架统一：** 四个问题共享同一套建模框架（P2/P3/P4间的差异仅在于设备集合规模和是否包含购买决策），便于代码维护和结果复现。

3. **求解效率高：** CP-SAT的OptionalIntervalVar和OnlyEnforceIf机制可在单一约束传播框架下同时处理设备选择（离散）和时间排序（连续），四个问题均在数秒至数十秒内达到最优解。

4. **校验机制完善：** 调度结果通过六项校验条件验证，确保模型输出与约束条件一致。

## 11.2 模型局限性

1. **目标函数单一：** 仅以makespan最小为目标，未考虑设备折旧、能耗等成本因素。

2. **预算未被充分消耗：** 采购费用445000元低于预算上限500000元，说明在makespan已达最优的前提下，额外预算无法进一步缩短工期。

3. **静态调度：** 不具备鲁棒性，未考虑设备故障或调度扰动。

4. **C车间轮询顺序为预设：** 该顺序基于经验设定，未通过模型优化验证。

## 11.3 推广方向

本模型框架可推广至：更多车间、更多班组的制造调度；结合工序优先级差异的加权makespan目标；考虑设备租赁而非购买的调度优化；引入随机加工时间或运输时间的鲁棒调度。

---

# 十二、参考文献

[1] Google OR-Tools. CP-SAT Solver Documentation. https://developers.google.com/optimization

[2] 2026 MCM Problem B. Multi-Process Coordination Scheduling Problem.

[3] OR-Tools Team. "OptionalIntervalVar and OnlyEnforceIf in CP-SAT." Google Developers Blog.

[4] 江贺等. 求解资源约束项目调度的CPSAT方法. 运筹学学报, 2022.

[5] 陈浩哲等. 多工厂多阶段流水线调度问题的Benders分解算法. 中国管理科学, 2021.

---

# 附录

## A.1 整体架构

```
src/
├── data_loader.py      # Excel数据读取与解析
├── preprocessing.py    # 工序展开、优先关系建立
├── models.py          # 数据类定义
├── time_utils.py      # 加工时间与运输时间计算
├── solver_p1.py       # 问题一CP-SAT模型
├── solver_p2.py       # 问题二CP-SAT模型
├── solver_p3.py       # 问题三CP-SAT模型
├── solver_p4.py       # 问题四CP-SAT模型（购置联合优化）
└── generate_result_tables.py  # 结果导出Excel工具
```

## A.2 核心建模：OnlyEnforceIf实现设备选择与时间变量联动

```python
# selected: start == proc_start, end == start + proc_time
c1 = model.Add(start == proc_start[pid])
c1.OnlyEnforceIf(sel)  # 仅当sel=1时激活
c2 = model.Add(end == start + proc_time)
c2.OnlyEnforceIf(sel)

# unselected: start == 0, end == 0
c3 = model.Add(start == 0)
c3.OnlyEnforceIf(sel.Not())  # 仅当sel=0时激活
c4 = model.Add(end == 0)
c4.OnlyEnforceIf(sel.Not())
```

## A.3 核心建模：Disjunctive运输顺序约束

```python
varname = 'i_before_j_' + pi + '_' + pj + '_' + eq
i_before_j = model.NewBoolVar(varname)
# i before j: start_j >= end_i + travel_ij
c_ij = model.Add(start_j >= end_i + travel_ij)
c_ij.OnlyEnforceIf(i_before_j)
# j before i: start_i >= end_j + travel_ji
c_ji = model.Add(start_i >= end_j + travel_ji)
c_ji.OnlyEnforceIf(i_before_j.Not())
# Both constraints only apply when both ops are selected
c_ij.OnlyEnforceIf(sel_i)
c_ij.OnlyEnforceIf(sel_j)
c_ji.OnlyEnforceIf(sel_i)
c_ji.OnlyEnforceIf(sel_j)
```

## A.4 问题四购买约束（buy <= sum(uses)）

```python
for (et, crew, idx), buy_var in buy_vars.items():
    uses = [sel for pid in processes if (pid, et, crew, idx) in pot_select]
    if uses:
        model.Add(buy_var <= sum(uses))  # bought -> must be used at least once
```

## A.5 时间计算公式

```python
def calculate_processing_time(workload, efficiency):
    hours = workload / efficiency
    return math.ceil(hours * 3600)  # d_p_k = ceil(q_p / v_p_k * 3600)

def calculate_transport_time(distance_m, speed_mps):
    seconds = distance_m / speed_mps
    return math.ceil(seconds)  # tau_i_j_e = ceil(D_i_j / u_e)
```

## A.6 校验函数结构

校验函数包含六项检查：①车间内优先级（A1→A2→A3等）；②设备无重叠（含车间间运输间隔）；③所有工序均已调度；④班组约束；⑤所有所需设备类型已安排；⑥初始运输（首作业>=crew→workshop时间）；⑦工序完成时间=所有参与设备结束时间最大值。
