"""
Fenrir 统一草稿存档（双文件拆分版）。

按内容大小拆成两个文件：
  data/workspace.json  —— 大体积文档内容（每个 tab 的 html / marks / floats）
  data/settings.json   —— 小体积配置（tab 名、用户词库、对比窗口数据、版本号）

这样频繁的「改 tab 名 / 改用户词库」不需要重写几 MB 的 HTML，
频繁的「打字保存」也不需要重写 tab 名列表。

内存里仍然合并成一份 _state 字典，main.py 的所有调用方无感知。
写入采用「读-改-写 + 临时文件原子替换」，任何异常都不会留下半个 JSON。
"""
import io
import json
import os
import time

# draft_store.py 现在位于 src/ 子目录，项目根目录是其父目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
WORKSPACE = os.path.join(DATA_DIR, 'workspace.json')   # 文档内容（大）
SETTINGS = os.path.join(DATA_DIR, 'settings.json')     # 配置元数据（小）
VERSION = 3

LEGACY_TAB_LIMIT = 30
LEGACY_COMPARE_LIMIT = 10

# 专利模板（原 data/model_*.html），内嵌为常量，通过 get_template() 访问
TEMPLATES = {
    'oa': '<html><body style="font-size:12pt;color:#dfe1e2;background-color:#19232d;"><p>申请人收到的审查意见通知书（一通.pdf），修改后的权利要求为：XXX。</p><p>请结合本发明、对比文件1、对比文件2的内容答复审查意见通知书，并列出权利要求1与对比文件1的特征对比表格，使本发明请求保护的技术方案具备专利法22条第3款规定的创造性。答复模板如下：</p><p>回答按以下规则:1. 只基于可验证事实，不编造任何信息。2.不确定就直接说「暂无可靠依据」。3.全部原创重述，不直接照搬原文。4.引用/标注用MLA格式。5.风格:介于学术与口语之间，正式但不生硬。6.多用短句、常用词，少复杂长句。</p><p>所有对话优先客观中立的分析，不要迎合我，也不要提供情绪价值。可以直接指出我表达里的问题，包括逻辑漏洞、认知偏差或者不成立的地方，越直接越好。只就事论事做理性分析和纠错。</p><p>创造性、非显而易见性的的判断基于以下原则：</p><p>发明的创造性，是指与现有技术相比，该发明有突出的实质性特点和显著的进步。发明有突出的实质性特点，是指对所属技术领域的技术人员来说，发明相对于现有技术是"非显而易见"的。</p><p>具体的，要从最接近的现有技术和发明实际解决的技术问题出发，判断要求保护的发明对本领域的技术人员来说是否显而易见。判断过程中，要确定的是现有技术整体上是否存在某种技术启示，即现有技术中是否给出将上述区别特征应用到该最接近的现有技术以解决其存在的技术问题（即发明实际解决的技术问题）的启示，这种启示会使本领域的技术人员在面对所述技术问题时，有动机改进该最接近的现有技术并获得要求保护的发明。</p><p>现有技术（最接近的现有技术或其他对比文件）均未公开区别特征在本申请中的作用。例如，对比文件未公开涉案专利特殊流线型的子弹形针尖部，对比文件未教导"将微针针尖部的外表面的切线倾斜角度由下至上逐渐变小以便于刺入皮肤"，因此在对比文件的基础上，并无动机设置相应形状结构的针尖部。</p><p>最接近的现有技术以外的对比文件虽然公开了区别特征在本申请中的作用，但二者存在结合障碍。例如，对比文件虽教导了设置尖端点有利于穿刺，但二者的技术构思是相反的，无结合动机，因此不能得到目标微针。</p><p>区别特征在本申请中的作用虽可预期，但在最接近的现有技术的基础上无动机调整，即存在反向教导。例如，对比文件中明确记载了无法制备得到具有尖端结构的微针，在此基础上，即使设置尖端点以利于穿刺容易想到，亦没有动机调整也不能制备得到目标微针。</p><p> "非显而易见"和"预料不到的技术效果"是创造性的充分条件，但不是必要条件。对于"非显而易见"的技术方案，具有有益的技术效果即可，并不要求预料不到的技术效果。涉案专利未提供数据证明其在本领域处于领先的技术水平，但根据一般认知可以预期所限定的技术特征有利于穿刺和/或提高强度，在创造性判断时，亦应当认可其具有有益的效果。由于在对比文件1、对比文件2或对比文件6的基础上均无动机调整得到涉案专利的方案，即涉案专利的方案是"非显而易见"的，上述有益的效果已足以体现其具有显著的进步，进而具有创造性。</p><p>基于以上分析，即使技术方案很"简单"、很"日常"，只要没有证据能够说明方案容易得到，即方案是"非显而易见"的，仍然有希望获得授权。</p><p></p><p style="font-weight:bold;">尊敬的审查员：</p><p>申请人收到了您发出的审查意见通知书，现针对通知书中指出的缺陷进行如下修改及意见陈述。</p><p style="font-weight:bold;">1. 申请文件的修改</p><p>将权x进一步限定的内容补入原权利要求1。</p><p>将说明书第[0000]段的内容<span style="text-decoration: underline;">&lt;INSERT_CONTENT&gt;</span>补入原权利要求1。</p><p style="font-weight:bold;">2. 创造性的意见陈述</p><p style="font-weight:bold;">2.1 区别技术特征分析</p><p>对比文件1(CN123456789A)公开了XXXX，其核心技术内容包括：1）2）3）。</p><p>本发明权利要求1请求保护的技术方案整体解决的技术问题是：XXX。</p><p>将对比文件1作为本申请的最接近技术，本申请权利要求1与对比文件1的技术差异主要体现在：1）2）3）。</p><p>本发明权利要求1与对比文件1相比，技术特征对比表格如下：</p><p>权利要求1   本发明  对比文件1  具体说明</p><p>区别特征1</p><p>区别特征2</p><p>区别特征3</p><p style="font-weight:bold;">2.2 区别技术特征确定以及各区别特征所要实际解决的技术问题：</p><p>基于上述分析可知，本发明专利申请权利要求1要求保护的技术方案与最接近对比文件1公开的技术方案相比，区别技术特征至少包括：</p><p style="font-weight:bold;">区别技术特征1：&lt;区别技术特征1&gt;</p><p>基于区别技术特征1，其实际所要解决的技术问题是：XXX</p><p style="font-weight:bold;">区别技术特征2：&lt;区别技术特征2&gt;</p><p>基于区别技术特征2，其实际所要解决的技术问题是：XXX</p><p style="font-weight:bold;">区别技术特征3：&lt;区别技术特征3&gt;</p><p>基于区别技术特征3，其实际所要解决的技术问题是：XXX</p><p style="font-weight:bold;">2.3 非显而易见性论述</p><p>对比文件2(CN123456789A)公开了XXXX。</p><p>对比文件3(CN123456789A)公开了XXXX。</p><p style="font-weight:bold;">对于区别技术特征1：&lt;区别技术特征1&gt;。同时，区别技术特征1未被对比文件2~4公开，对比文件2~4未给出将区别特征与对比文件1相结合的技术启示。因此，区别技术特征1相对于本领域普通技术人员是非显而易见的。</p><p style="font-weight:bold;">对于区别技术特征2：&lt;区别技术特征2&gt;。同时，区别技术特征2未被对比文件2~4公开，对比文件2~4未给出将区别特征与对比文件1相结合的技术启示。因此，区别技术特征2相对于本领域普通技术人员是非显而易见的。</p><p style="font-weight:bold;">对于区别技术特征3：&lt;区别技术特征3&gt;。同时，区别技术特征3未被对比文件2~4公开，对比文件2~4未给出将区别特征与对比文件1相结合的技术启示。因此，区别技术特征3相对于本领域普通技术人员是非显而易见的。</p><p style="font-weight:bold;">3. 结论</p><p>以上，在对比文件1的基础上结合对比文件<span style="text-decoration: underline;">2~x</span>以及本领域的公知常识得到权利要求1所要求保护的技术方案，相对于本领域普通技术人员来说是非显而易见的，权利要求1具备突出的实质性特点和显著的进步，具备专利法22条第3款规定的创造性。</p><p>通过上述修改及意见陈述，修改后的申请文件已经克服了审查意见中指出的全部缺陷，具备授权前景，望授权回盼。</p></body></html>',
    'des': '<html><body style="font-size:12pt;color:#dfe1e2;background-color:#19232d;"><p style="font-weight:bold;">申请人：</p><p style="font-weight:bold;">社会统一信用代码：</p><p style="font-weight:bold;">地址：</p><p style="font-weight:bold;">发明人：</p><p style="font-weight:bold;">&lt;标题&gt;</p><p style="font-weight:bold;">技术领域</p><p>本发明涉及&lt;技术领域&gt;，具体说是一种&lt;标题&gt;。</p><p style="font-weight:bold;">背景技术</p><p>&lt;背景技术&gt;</p><p style="font-weight:bold;">发明内容</p><p>本发明的目的是提供一种&lt;标题&gt;，从根本上解决了上述问题，其具有&lt;优点&gt;等优点。</p><p>为实现上述目的，本发明提供了如下技术方案：该&lt;标题&gt;，其技术要点是：</p><p style="font-weight:bold;">本发明的有益效果：&lt;有益效果&gt;</p><p>整体技术方案上，</p><p>具体结构上，</p><p style="font-weight:bold;">附图说明</p><p>图1为本发明的主视结构示意图。</p><p>图2为本发明的等轴侧视结构示意图。</p><p style="font-weight:bold;">具体实施方式</p><p>以下结合图1，通过具体实施例详细说明本发明的具体内容。&lt;具体实施方式&gt;</p><p style="font-weight:bold;">附图标记说明：&lt;附图标记&gt;</p><p>背景技术撰写要求如下：</p><p> 1.检索与该技术方案最接近的现有技术。<p> 2.检索10篇以上，在现有的专利公开文献、非专利公开文献、公知常识中，继续检索区别技术特征是否被公开，对比文件是否给出了将区别特征与对比文件1相结合的技术启示。</p><p> 3.根据专利法22条第3款，结合对比文件评价该技术方案的创造性。</p><p> 4.检查该技术方案是否符合专利法26条第3款 第4款的规定，如果不符合，请给出具体理由。</p><p> 5.检查该专利文本的形式错误，如错别字，语句不通顺等。</p><p> 内容说明：</p><p> 对比文件尽量用专利公开号，如CN123456789A；对比文件用D代替，如对比文件1、2，用D1、D2代替。</p><p> 回答按以下规则:1. 只基于可验证事实，不编造任何信息。2.不确定就直接说「暂无可靠依据」。3.全部原创重述，不直接照搬原文。4.引用/标注用MLA格式。5.风格:介于学术与口语之间，正式但不生硬。6.多用短句、常用词，少复杂长句。</p><p> 所有对话优先客观中立的分析，不要迎合我，也不要提供情绪价值。可以直接指出我表达里的问题，包括逻辑漏洞、认知偏差或者不成立的地方，越直接越好。只就事论事做理性分析和纠错。</p></body></html>',
    'claim': '<html><body style="font-size:12pt;color:#dfe1e2; background-color:#19232d;"><p style="font-weight:bold">1. 一种&lt;TITLE&gt;，其特征在于：包括，。</p><p style="font-weight:bold">2. 根据权利要求1所述的&lt;TITLE&gt;，其特征在于：xxx。</p><p style="font-weight:bold">3. 根据权利要求1或2所述的&lt;TITLE&gt;，其特征在于：xxx。</p></body></html>',
    're': '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd"><html><head><meta name="qrichtext" content="1" /><style type="text/css">p, li { white-space: pre-wrap; }</style></head><body style=" font-family:\'SimSun\'; font-size:9pt; font-weight:400; font-style:normal;"><p>尊敬的复审和无效审理部：</p><p>申请人针对申请号&lt;APPNUM&gt;，专利名称&lt;TITLE&gt;，&lt;DATE&gt;发出的驳回决定提出复审请求。</p><p>1. 申请文件的修改</p><p>将权x进一步限定的内容补入原权1。</p><p>将说明书第[0000]段的内容&lt;INSERT_CONTENT&gt;补入原权1。</p><p>2. 创造性的意见陈述</p><p>2.1 区别技术特征分析</p><p>对比文件1(CN123456789A)公开了XXXX，其核心技术内容包括：1）2）3）。</p><p>本发明权利要求1请求保护的技术方案整体解决的技术问题是：XXX。</p><p>将对比文件1作为本申请的最接近技术，本申请权利要求1与对比文件1的技术差异主要体现在：1）2）3）。</p><p>本发明权利要求1与对比文件1相比，技术特征对比表格如下：</p><p>权利要求1 本发明 对比文件1 具体说明</p><p>区别特征1</p><p>区别特征2</p><p>区别特征3</p><p>2.2 区别技术特征确定以及各区别特征所要实际解决的技术问题：</p><p>基于上述分析可知，本发明专利申请权利要求1要求保护的技术方案与最接近对比文件1公开的技术方案相比，区别技术特征至少包括：</p><p>区别技术特征1：&lt;区别技术特征1&gt;</p><p>基于区别技术特征1，其实际所要解决的技术问题是：XXX</p><p>区别技术特征2：&lt;区别技术特征2&gt;</p><p>基于区别技术特征2，其实际所要解决的技术问题是：XXX</p><p>区别技术特征3：&lt;区别技术特征3&gt;</p><p>基于区别技术特征3，其实际所要解决的技术问题是：XXX</p><p>2.3 非显而易见性论述</p><p>对于区别特征1：&lt;区别特征1&gt;。因此，区别特征1相对于对比文件1是非显而易见的。</p><p>对于区别特征2：&lt;区别特征2&gt;。因此，区别特征2相对于对比文件1是非显而易见的。</p><p>对于区别特征3：&lt;区别特征3&gt;。因此，区别特征3相对于对比文件1是非显而易见的。</p><p>对比文件2(CN123456789A)公开了XXXX。</p><p>对比文件3(CN123456789A)公开了XXXX。</p><p>对于区别技术特征1：&lt;区别技术特征1&gt;。同时，区别技术特征1未被对比文件2~4公开，对比文件2~4未给出将区别特征与对比文件1相结合的技术启示。因此，区别技术特征1相对于本领域普通技术人员是非显而易见的。</p><p>对于区别技术特征2：&lt;区别技术特征2&gt;。同时，区别技术特征2未被对比文件2~4公开，对比文件2~4未给出将区别特征与对比文件1相结合的技术启示。因此，区别技术特征2相对于本领域普通技术人员是非显而易见的。</p><p>对于区别技术特征3：&lt;区别技术特征3&gt;。同时，区别技术特征3未被对比文件2~4公开，对比文件2~4未给出将区别特征与对比文件1相结合的技术启示。因此，区别技术特征3相对于本领域普通技术人员是非显而易见的。</p><p>3. 结论</p><p>以上，在对比文件1的基础上结合对比文件2~x以及本领域的公知常识得到权利要求1所要求保护的技术方案，相对于本领域普通技术人员来说是非显而易见的，权利要求1具备突出的实质性特点和显著的进步，具备专利法22条第3款规定的创造性。</p><p>申请人认为，通过上述修改及意见陈述，修改后的申请文件已经克服了驳回决定中指出的全部缺陷，具备授权前景，请求撤销驳回决定。</p></body></html>',
    'invalid': '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd"><html><head><meta name="qrichtext" content="1" /><style type="text/css">p, li { white-space: pre-wrap; }</style></head><body style=" font-family:\'SimSun\'; font-size:9pt; font-weight:400; font-style:normal;"><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">尊敬的复审和无效审理部</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">： </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">申请人针对申请号&lt;APPNUM&gt;，专利名称&lt;TITLE&gt;，申请日为&lt;DATE&gt;的发明专利提出无效宣告请求。 </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">一、 无效宣告请求所针对的权利要求 </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">1.</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;"> 一种&lt;TITLE&gt;，</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">其特征在于</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">： </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">2.</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;"> 根据权利要求1所述的&lt;TITLE&gt;，</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">其特征在于</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">： </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">二、无效宣告理由</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;"> </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">2.1</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;"> </span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">引用的证据</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;"> </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">证据1：</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">申请公布日为2009年01月01日，申请公布号为CN</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">1234</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">56A的中国发明专利申请的复印件； </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">证据2：</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">申请公布日为2009年01月01日，申请公布号为CN</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">1234</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">56A的中国发明专利申请的复印件； </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">证据3：</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">申请公布日为2009年01月01日，申请公布号为CN</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">1234</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">56A的中国发明专利申请的复印件； </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">2.2</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;"> 具体</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">无效理由</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;"> </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">2.2.1</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;"> </span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">无效理由</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;"> </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">针对上述专利，请求人提出了无效宣告请求，请求宣告本专利全部无效，</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">无效理由</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">是：</span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">权利要求1~6的技术方案不具备新颖性，不符合中华人民共和国专利法（下称专利法）第22条第2款的规定。</span></p><p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-size:12pt; color:#dfe1e2;"><br /></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">权利要求1~6的技术方案不具备创造性，不符合中华人民共和国专利法（下称专利法）第22条第3款的规定。</span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">权利要求1相对于</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">证据1、2</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">的组合不具备创造性。</span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">权利要求2相对于</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">证据1、2</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">的组合不具备创造性。</span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">权利要求3相对于</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">证据1、3</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">的组合不具备创造性。</span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">权利要求4相对于</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">证据1、3</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">的组合不具备创造性。</span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">权利要求5相对于</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">证据1、3</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">的组合不具备创造性。</span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">权利要求6相对于</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">证据1、3</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">的组合不具备创造性。 </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">1）权利要求1不具备创造性的理由 </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">对比文件</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">1(CN</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">1234</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">56789)公开了&lt;主题名称&gt;，并具体公开了&lt;具体技术方案&gt;。</span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">权1请求保护一种&lt;TITLE&gt;，与</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">对比文件</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">1(CN</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">1234</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">56789)公开的技术方案相比，其区别技术特征为： </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">区别特征1：</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">&lt;</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">区别特征1</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">&gt; </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">区别特征2：</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">&lt;</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">区别特征2</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">&gt; </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">区别特征3：</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">&lt;</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">区别特征3</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">&gt; </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">基于上述区别特征，权1相对于</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">对比文件</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">1所要实际解决的</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">技术问题为</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">：&lt;实际解决的技术问题&gt;</span></p><p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-size:12pt; color:#dfe1e2;"><br /></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">对于区别特征1：</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">&lt;</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">区别特征1</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">&gt;。因此，</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">区别特征1</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">相对于</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">对比文件</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">1是显而易见的。 </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">对于区别特征2：</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">&lt;</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">区别特征2</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">&gt;。因此，</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">区别特征2</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">相对于</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">对比文件</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">1是显而易见的。 </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">对于区别特征3：</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">&lt;</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">区别特征3</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">&gt;。因此，</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">区别特征3</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">相对于</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">对比文件</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">1是显而易见的。 </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">由此可知，在</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">证据1</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">的基础上结合</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">证据2、3</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">以及本领域的常用技术手段得出权利要求1的技术方案，对于本领域普通技术人员来说是显而易见的，因此该权利要求1所要求保护的技术方案不具有实质性特点和进步，因此不具备专利法跌22条第3款规定的创造性。</span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">2）权利要求2~6不符合专利法第22条第3款规定的创造性的理由</span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">权利要求2对权利要求1做了进一步限定。</span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">因此，在其所引用的权利要求不具备创造性的情况下，该权利要求也不具备专利法第22条第3款规定的创造性。</span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">三、</span><span style=" font-size:12pt; font-weight:600; color:#dfe1e2; background-color:#19232d;">结论</span><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;"> </span></p><p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-size:12pt; color:#dfe1e2; background-color:#19232d;">基于上述理由，请求人请求宣告上述专利全部无效。 </span></p></body></html>',
}


def get_template(name):
    """按名称取专利模板 HTML，名称对应原 data/model_*.html 文件。"""
    return TEMPLATES.get(name, '')


# 内存里的合并状态：_state['main']['tabs'] 来自 docs.json，
# 其他字段（names/userwords/compare/version）来自 settings.json
_state = None
_docs = None     # 只含 {'tabs': [...]}


def _blank():
    return {
        'version': VERSION,
        'main': {'names': [], 'userwords': '', 'tabs': []},
        'compare': {'main': {'text': '', 'marks': ''}, 'files': []},
        # 用户自定义的「预设格式」关键词表（每行一条，\n 分隔）。
        # 空串 = 使用 main.py 内置的 FORMAT_ARRAY_BASE。
        'format_preset': '',
    }


def _read_file(path, default=''):
    try:
        with io.open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return default


def _write_json(path, obj):
    """原子写：先写 .tmp 再 os.replace，防止崩溃留半个文件。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = path + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False, separators=(',', ':')))
    os.replace(tmp, path)


def _migrate():
    """从旧版散文件构造 workspace，不删除任何旧文件。"""
    state = _blank()
    names = [n.strip() for n in
             _read_file(os.path.join(DATA_DIR, 'tab_name.txt')).split('，') if n.strip()]
    state['main']['names'] = names
    state['main']['userwords'] = _read_file(os.path.join(DATA_DIR, 'userwords_saver.txt'))

    tabs = []
    for i in range(1, LEGACY_TAB_LIMIT + 1):
        html = _read_file(os.path.join(DATA_DIR, 'text_saver_%d.html' % i))
        marks = _read_file(os.path.join(DATA_DIR, 'marks_saver_%d.txt' % i))
        tabs.append({'html': html, 'marks': marks})
    while tabs and not tabs[-1]['html'] and not tabs[-1]['marks']:
        tabs.pop()
    state['main']['tabs'] = tabs

    comp = state['compare']
    comp['main'] = {
        'text': _read_file(os.path.join(DATA_DIR, 'text_saver_compare_main.txt')),
        'marks': _read_file(os.path.join(DATA_DIR, 'marks_saver_compare_main.txt')),
    }
    files = []
    for i in range(1, LEGACY_COMPARE_LIMIT + 1):
        files.append({
            'text': _read_file(os.path.join(DATA_DIR, 'text_saver_compare_%d.txt' % i)),
            'marks': _read_file(os.path.join(DATA_DIR, 'marks_saver_compare_%d.txt' % i)),
        })
    while files and not files[-1]['text'] and not files[-1]['marks']:
        files.pop()
    comp['files'] = files
    state['migrated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    return state


def _split_and_load(legacy_state=None):
    """把内存 _state 拆成 docs / settings 两部分并落盘。
    返回合并后的 state（供调用方继续用）。"""
    global _state, _docs
    if legacy_state is not None:
        _state = legacy_state
    # docs.json 只放 tabs
    _docs = {'tabs': (_state.get('main') or {}).get('tabs') or []}
    # settings.json 放其余所有字段
    settings = {
        'version': _state.get('version', VERSION),
        'names': (_state.get('main') or {}).get('names') or [],
        'userwords': (_state.get('main') or {}).get('userwords') or '',
        'compare': _state.get('compare') or {'main': {'text': '', 'marks': ''}, 'files': []},
        'format_preset': _state.get('format_preset') or '',
        'ai_check': _state.get('ai_check') or {},
    }
    if 'migrated_at' in _state:
        settings['migrated_at'] = _state['migrated_at']
    _write_json(WORKSPACE, _docs)
    _write_json(SETTINGS, settings)
    return _state


def ensure_loaded(force=False):
    """加载 workspace（docs.json + settings.json 合并）。
    - 新格式（v3+）：两文件分别读，合并成内存态
    - 旧格式（v2 单文件 workspace.json）：自动迁移拆分
    - 文件都不存在：从散文件迁移（_migrate）
    """
    global _state, _docs
    if _state is not None and not force:
        return _state

    # 先试新格式：settings.json + workspace.json（docs）
    settings_raw = None
    docs_raw = None
    try:
        with io.open(SETTINGS, 'r', encoding='utf-8') as f:
            settings_raw = json.load(f)
    except Exception:
        settings_raw = None
    try:
        with io.open(WORKSPACE, 'r', encoding='utf-8') as f:
            docs_raw = json.load(f)
    except Exception:
        docs_raw = None

    if isinstance(settings_raw, dict) and isinstance(docs_raw, dict) and 'tabs' in docs_raw:
        # 新格式：合并
        state = _blank()
        state['main']['names'] = settings_raw.get('names') or []
        state['main']['userwords'] = settings_raw.get('userwords') or ''
        state['main']['tabs'] = docs_raw.get('tabs') or []
        state['compare'] = settings_raw.get('compare') or state['compare']
        state['version'] = settings_raw.get('version', VERSION)
        state['format_preset'] = settings_raw.get('format_preset') or ''
        state['ai_check'] = settings_raw.get('ai_check') or {}
        if 'migrated_at' in settings_raw:
            state['migrated_at'] = settings_raw['migrated_at']
        _state = state
        _docs = docs_raw
        return state

    # 兼容旧格式 v2：workspace.json 单文件含 main.tabs + 其他字段
    old_raw = None
    try:
        with io.open(WORKSPACE, 'r', encoding='utf-8') as f:
            old_raw = json.load(f)
    except Exception:
        old_raw = None
    if isinstance(old_raw, dict) and 'main' in old_raw:
        # 旧单文件格式 → 拆分落盘
        state = _blank()
        state.update(old_raw)
        if 'compare' not in state:
            state['compare'] = _blank()['compare']
        _split_and_load(state)
        return state

    # 都没有 → 从散文件迁移
    _state = _migrate()
    _split_and_load(_state)
    return _state


def _save():
    """根据改动位置决定写哪个文件：
    - 改动只涉及 names/userwords/compare → 只写 settings.json
    - 改动涉及 tabs/html/marks/floats → 写 docs.json（同时保留 settings.json 已落盘的状态）
    简化：保守起见，_save() 同时写两个文件，差异写盘由上层 set_* 的 diff 判断控制。"""
    global _docs
    # 从内存 _state 重新拆出 docs 和 settings
    _docs = {'tabs': (_state.get('main') or {}).get('tabs') or []}
    settings = {
        'version': _state.get('version', VERSION),
        'names': (_state.get('main') or {}).get('names') or [],
        'userwords': (_state.get('main') or {}).get('userwords') or '',
        'compare': _state.get('compare') or {'main': {'text': '', 'marks': ''}, 'files': []},
        'format_preset': _state.get('format_preset') or '',
        'ai_check': _state.get('ai_check') or {},
    }
    if 'migrated_at' in _state:
        settings['migrated_at'] = _state['migrated_at']
    _write_json(WORKSPACE, _docs)
    _write_json(SETTINGS, settings)


# ---------------- 主窗口：文档 / 名称 / 词库 ----------------
def main_state():
    return ensure_loaded()['main']


def main_names():
    return list(main_state().get('names') or [])


def set_main_names(names):
    state = main_state()
    names = list(names)
    if state.get('names') != names:
        state['names'] = names
        _save()


def main_userwords():
    return main_state().get('userwords') or ''


def set_main_userwords(text):
    state = main_state()
    if state.get('userwords') != text:
        state['userwords'] = text
        _save()


def main_format_preset():
    """用户自定义的「预设格式」关键词表原文（每行一条）。
    返回空串表示未自定义，调用方应回落到 main.py 的 FORMAT_ARRAY_BASE。"""
    return ensure_loaded().get('format_preset') or ''


def set_main_format_preset(text):
    """保存「预设格式」关键词表到 data/settings.json；传空串即恢复内置默认。"""
    state = ensure_loaded()
    text = text or ''
    if (state.get('format_preset') or '') != text:
        state['format_preset'] = text
        _save()


def ai_config():
    """AI 接口设置（火山方舟）。返回本地保存的原始字典，未配置时为 {}。"""
    return dict(ensure_loaded().get('ai_check') or {})


def set_ai_config(cfg):
    """把 AI 接口设置写入 data/settings.json；密钥只存本机，不进日志。"""
    state = ensure_loaded()
    state['ai_check'] = dict(cfg or {})
    _save()


def _ensure_tabs(count):
    tabs = main_state()['tabs']
    while len(tabs) < count:
        tabs.append({'html': '', 'marks': ''})


def main_tab_count():
    return len(main_state()['tabs'])


def get_tab(index):
    """返回 (html, marks)。越界自动补空，调用方无需先建文件。"""
    _ensure_tabs(index + 1)
    item = main_state()['tabs'][index]
    return item.get('html') or '', item.get('marks') or ''


def set_tab(index, html=None, marks=None, name=None):
    """按需写入：内容未变化时不重写整个 workspace（失焦保存很频繁）。"""
    _ensure_tabs(index + 1)
    item = main_state()['tabs'][index]
    changed = False
    if html is not None and item.get('html') != html:
        item['html'] = html
        changed = True
    if marks is not None and item.get('marks') != marks:
        item['marks'] = marks
        changed = True
    if name is not None:
        names = main_state()['names']
        while len(names) <= index:
            names.append('文档%d' % (len(names) + 1))
            changed = True
        if names[index] != name:
            names[index] = name
            changed = True
    if changed:
        _save()


# ---- 浮动图片（浮于文字上方）的位置与数据，与 html 分开存 ----
def get_tab_floats(index):
    """返回该文档的浮动图片列表（每项：uri/block/x/dy/w/h）。"""
    _ensure_tabs(index + 1)
    return list(main_state()['tabs'][index].get('floats') or [])


def set_tab_floats(index, floats):
    _ensure_tabs(index + 1)
    item = main_state()['tabs'][index]
    floats = list(floats or [])
    if item.get('floats') != floats:
        item['floats'] = floats
        _save()


# ---- 申请人 / 发明人信息，与 html 分开存（每个文档一份） ----
def get_tab_party(index):
    """返回该文档的申请人/发明人信息；没有则空 dict。"""
    _ensure_tabs(index + 1)
    return dict(main_state()['tabs'][index].get('party') or {})


def set_tab_party(index, party):
    """写入该文档的申请人/发明人信息（内容没变不落盘）。"""
    _ensure_tabs(index + 1)
    item = main_state()['tabs'][index]
    party = party or {}
    if item.get('party') != party:
        item['party'] = party
        _save()


def save_main_snapshot(names, userwords, htmls, marks_list):
    """一次性写入全部文档（关闭窗口 / 保存草稿时使用，只落盘一次）。"""
    state = ensure_loaded()
    old_tabs = state.get('main', {}).get('tabs') or []
    tabs = []
    for i in range(max(len(names), len(htmls), len(marks_list))):
        item = {'html': htmls[i] if i < len(htmls) else '',
                'marks': marks_list[i] if i < len(marks_list) else ''}
        if i < len(old_tabs) and old_tabs[i].get('floats'):
            item['floats'] = old_tabs[i]['floats']
        # 申请人/发明人信息不在界面快照里传，按原样保留，别在关闭时丢掉
        if i < len(old_tabs) and old_tabs[i].get('party'):
            item['party'] = old_tabs[i]['party']
        tabs.append(item)
    state['main'] = {
        'names': list(names),
        'userwords': userwords,
        'tabs': tabs,
    }
    _save()


def drop_last_tabs(count):
    """删除末尾若干文档（保留前 count 个），用于关闭新增文档。"""
    tabs = main_state()['tabs']
    if len(tabs) > count:
        del tabs[count:]
        _save()


# ---------------- 对比窗口：本发明 + N 个对比文件 ----------------
def compare_state():
    return ensure_loaded()['compare']


def get_compare_main():
    item = compare_state().get('main') or {}
    return item.get('text') or '', item.get('marks') or ''


def set_compare_main(text=None, marks=None):
    item = compare_state().setdefault('main', {'text': '', 'marks': ''})
    if text is not None:
        item['text'] = text
    if marks is not None:
        item['marks'] = marks
    _save()


def get_compare_file(index):
    files = compare_state()['files']
    while len(files) <= index:
        files.append({'text': '', 'marks': ''})
    item = files[index]
    return item.get('text') or '', item.get('marks') or ''


def set_compare_file(index, text=None, marks=None):
    files = compare_state()['files']
    while len(files) <= index:
        files.append({'text': '', 'marks': ''})
    if text is not None:
        files[index]['text'] = text
    if marks is not None:
        files[index]['marks'] = marks
    _save()


# ---------------- 迁移后的旧文件清理 ----------------
def legacy_paths():
    """列出已被 workspace.json 取代、可以安全删除的旧存档文件。"""
    if not os.path.isfile(WORKSPACE):
        return []
    paths = []
    for i in range(1, LEGACY_TAB_LIMIT + 1):
        paths.append('text_saver_%d.html' % i)
        paths.append('marks_saver_%d.txt' % i)
    for i in range(1, LEGACY_COMPARE_LIMIT + 1):
        paths.append('text_saver_compare_%d.txt' % i)
        paths.append('marks_saver_compare_%d.txt' % i)
    paths += ['text_saver_compare_main.txt', 'marks_saver_compare_main.txt',
              'tab_name.txt', 'userwords_saver.txt']
    return [p for p in paths if os.path.isfile(os.path.join(DATA_DIR, p))]


def cleanup_legacy():
    """删除旧散文件，返回 (已删除数, 失败列表)。调用方应先做备份。"""
    removed, errors = 0, []
    for name in legacy_paths():
        try:
            os.remove(os.path.join(DATA_DIR, name))
            removed += 1
        except Exception as exc:
            errors.append((name, str(exc)))
    return removed, errors
