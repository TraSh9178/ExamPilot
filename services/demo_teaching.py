"""Reviewed offline calculus lessons. No account state or generation required."""

# Three reasoning steps, a worked example and a common mistake, in each UI language.
LESSONS = {
    'calc_limits': (
        ['A limit describes nearby values, even when the function has a hole.', 'Try substitution first. If it produces 0/0, simplify for nearby inputs.', 'Compare both sides; a two-sided limit requires the same value.'],
        'For (x² − 4)/(x − 2), factor the numerator into (x − 2)(x + 2). For x ≠ 2, cancel x − 2. The nearby values equal x + 2, so the limit at 2 is 4.',
        'Do not confuse an undefined f(2) with a nonexistent limit.',
        ['极限描述附近的函数值，即使目标点有空洞也可以有极限。', '先代入；若得到 0/0，再对附近的输入进行化简。', '分别观察左右两侧，双侧极限要求两侧趋向同一个值。'],
        '(x² − 4)/(x − 2) 的分子分解为 (x − 2)(x + 2)。当 x ≠ 2 时约去 x − 2，附近的函数值等于 x + 2，所以 x 趋近 2 时极限为 4。',
        'f(2) 未定义不代表极限不存在。'),
    'calc_derivatives': (
        ['The derivative measures instantaneous change, represented by a tangent slope.', 'Start with the secant quotient [f(x+h) − f(x)]/h, where h ≠ 0.', 'Simplify first, then take h → 0.'],
        'For f(x)=x², [(x+h)²−x²]/h = 2x+h. Taking h → 0 gives f′(x)=2x; at x=3 the tangent slope is 6.',
        'Substituting h=0 before simplifying creates an undefined quotient.',
        ['导数是瞬时变化率，也就是切线斜率。', '从割线斜率 [f(x+h) − f(x)]/h 开始，h ≠ 0。', '先化简，再令 h 趋近 0。'],
        '对 f(x)=x²，差商 [(x+h)²−x²]/h = 2x+h。令 h 趋近 0 得 f′(x)=2x；x=3 处的切线斜率为 6。',
        '不要在化简之前直接令 h=0。'),
    'calc_derivative_applications': (
        ['A derivative tells whether a function is increasing or decreasing.', 'Find interior critical points where f′=0 or the derivative is undefined.', 'Use sign changes to classify them; check endpoints when finding absolute extrema.'],
        'For f(x)=x²−4x on [0,5], f′(x)=2x−4 vanishes at 2. Compare f(0)=0, f(2)=−4 and f(5)=5: the minimum is −4 at 2, and the maximum is 5 at 5.',
        'A stationary point is only a candidate; f(x)=x³ has no extremum at 0.',
        ['导数的符号告诉我们函数在增加还是减少。', '先找区间内部 f′=0 或导数不存在的临界点。', '用符号变化分类；求绝对最值时也要检查端点。'],
        'f(x)=x²−4x 在 [0,5] 上的导数为 2x−4，在 x=2 处为零。比较 f(0)=0、f(2)=−4、f(5)=5，最小值是 −4，最大值是 5。',
        '驻点只是候选点；x³ 在 0 处导数为零但没有极值。'),
    'calc_limit_laws': (
        ['Limits distribute over sums and products when the component limits exist.', 'A quotient law also requires a nonzero denominator limit.', 'If direct substitution is indeterminate, simplify before applying the laws.'],
        'As x → 2, x² → 4 and 3x → 6. Therefore x²+3x → 10. For 1/(x−2), the denominator tends to zero, so the quotient law cannot be used.',
        '0/0 is an indeterminate form, not a value.',
        ['各部分极限存在时，可以对和、差、积分别取极限。', '商法则还要求分母的极限不为零。', '直接代入出现未定式时，应先化简。'],
        'x 趋近 2 时，x² 趋近 4，3x 趋近 6，所以 x²+3x 趋近 10。1/(x−2) 的分母极限为零，不能直接套用商法则。',
        '0/0 是未定式，不是一个答案。'),
    'calc_continuity': (
        ['Continuity joins the value at a point to the limit around it.', 'Check that f(a) exists and that the two-sided limit exists.', 'Then check that the limit equals f(a).'],
        'Let f(x)=(x²−4)/(x−2) for x≠2 and f(2)=k. The limit at 2 is 4, so continuity requires k=4.',
        'Matching only one side does not establish continuity.',
        ['连续性把某点的函数值与附近的极限连接起来。', '检查 f(a) 有定义，且双侧极限存在。', '最后检查极限等于 f(a)。'],
        '当 x≠2 时令 f(x)=(x²−4)/(x−2)，并定义 f(2)=k。因为附近的极限为 4，所以只有 k=4 时函数在 2 处连续。',
        '只检查一侧是不够的。'),
    'calc_trig_limits': (
        ['The standard limit sin(u)/u → 1 uses radians.', 'Rewrite the expression so the numerator angle and denominator match.', 'Track the extra scale factors outside the standard ratio.'],
        'sin(3x)/x = 3·sin(3x)/(3x). As x → 0, the ratio tends to 1, giving a limit of 3.',
        'The standard formula is not valid with degree measure.',
        ['标准极限 sin(u)/u → 1 使用弧度制。', '将式子改写，使分子的角度与分母一致。', '把额外的倍数放在标准比值外面。'],
        'sin(3x)/x = 3·sin(3x)/(3x)。x 趋近 0 时，后面的比值趋近 1，所以极限为 3。',
        '使用角度制时不能直接套用这个标准极限。'),
    'calc_differentiation_rules': (
        ['Identify whether the expression is a sum, product or quotient.', 'Differentiate each part with the corresponding rule.', 'Simplify after applying the rule and respect the original domain.'],
        'For f(x)=x²sin(x), use the product rule: f′(x)=2x sin(x)+x² cos(x). Both factors contribute a term.',
        'The derivative of a product is not the product of the derivatives.',
        ['先判断表达式是和、积还是商。', '用对应法则对每个部分求导。', '应用法则后再化简，并保留原定义域的限制。'],
        'f(x)=x²sin(x) 使用乘积法则：f′(x)=2x sin(x)+x²cos(x)。两个因子分别求导，得到两项。',
        '乘积的导数不等于两个导数的乘积。'),
    'calc_chain_rule': (
        ['Identify the outer function and the inner function.', 'Differentiate the outer function while keeping its input unchanged.', 'Multiply by the derivative of the inner function.'],
        'For y=(3x²+1)⁴, the outer derivative is 4(3x²+1)³ and the inner derivative is 6x. Therefore y′=24x(3x²+1)³.',
        'Do not omit the inner derivative.',
        ['辨认外层函数和内层函数。', '对外层求导时暂时保留内层不变。', '最后乘以内层函数的导数。'],
        'y=(3x²+1)⁴ 的外层求导得到 4(3x²+1)³，内层导数是 6x，因此 y′=24x(3x²+1)³。',
        '不要漏乘内层导数。'),
    'calc_implicit_differentiation': (
        ['Treat y as a function of x even when it is not isolated.', 'Differentiate both sides, using the chain rule on every y term.', 'Collect the y′ terms and solve where their coefficient is nonzero.'],
        'From x²+y²=25, differentiation gives 2x+2y y′=0. Thus y′=−x/y for y≠0. At (3,4), the slope is −3/4.',
        'Differentiating y² gives 2y y′, not just 2y.',
        ['即使没有解出 y，也要把 y 当作 x 的函数。', '两边对 x 求导，含 y 的项使用链式法则。', '收集 y′ 并求解，注意不能除以零。'],
        '由 x²+y²=25 得 2x+2y y′=0，所以 y≠0 时 y′=−x/y。在 (3,4) 处斜率为 −3/4。',
        'y² 对 x 求导是 2y y′，不能漏掉 y′。'),
    'calc_related_rates': (
        ['Write an equation connecting quantities that change with time.', 'Differentiate the equation with respect to time before substituting the snapshot values.', 'Insert the given rates and state units for the unknown rate.'],
        'For a circle A=πr², dA/dt=2πr·dr/dt. At r=3 cm and dr/dt=2 cm/s, dA/dt=12π cm²/s.',
        'Substituting a changing radius as a constant before differentiating loses its rate.',
        ['写出随时间变化的量之间的关系式。', '先对时间求导，再代入某一时刻的数值。', '代入已知变化率，求出未知变化率并写上单位。'],
        '圆面积 A=πr²，所以 dA/dt=2πr·dr/dt。当 r=3 cm、dr/dt=2 cm/s 时，面积变化率为 12π cm²/s。',
        '不要在求导前就把变化中的半径替换成常数。'),
    'calc_mean_value_theorem': (
        ['Verify continuity on [a,b] and differentiability on (a,b).', 'Compute the average slope [f(b)−f(a)]/(b−a).', 'Find an interior point c with f′(c) equal to that average.'],
        'For f(x)=x² on [1,3], the average slope is (9−1)/2=4. Since f′(c)=2c, c=2 satisfies the theorem.',
        'Without the hypotheses the theorem does not guarantee such a point.',
        ['先验证在闭区间 [a,b] 上连续，在开区间 (a,b) 内可导。', '计算平均斜率 [f(b)−f(a)]/(b−a)。', '寻找内部点 c，使 f′(c) 等于平均斜率。'],
        'f(x)=x² 在 [1,3] 上的平均斜率为 (9−1)/2=4。由 f′(c)=2c=4 得 c=2。',
        '不满足条件时，中值定理不能保证这个点存在。'),
    'calc_curve_sketching': (
        ['Check domain, intercepts and limiting behavior.', 'Use f′ to find increasing/decreasing intervals and extrema.', 'Use changes in the sign of f″ to identify concavity and inflection points.'],
        'For f(x)=x³−3x, f′=3(x²−1) gives critical points −1 and 1. Its signs are +,−,+, so there is a local maximum at −1 and minimum at 1. f″=6x changes sign at 0, giving an inflection point.',
        'f″=0 alone does not guarantee an inflection point; concavity must change.',
        ['先检查定义域、截距和极限行为。', '用 f′ 的符号判断增减区间及极值。', '用 f″ 的符号变化判断凹凸性和拐点。'],
        'f(x)=x³−3x 的导数为 3(x²−1)，临界点是 −1 和 1。导数符号依次为正、负、正，所以 −1 处极大，1 处极小。f″=6x 在 0 两侧变号，因此 0 是拐点。',
        '仅有 f″=0 不够，凹凸性必须发生变化。'),
    'calc_antiderivatives': (
        ['An antiderivative reverses differentiation.', 'For xⁿ with n≠−1, increase the exponent by one and divide by the new exponent.', 'Add the constant C and differentiate your result to check it.'],
        '∫(3x²+2) dx = x³+2x+C. Differentiating x³+2x+C gives 3x²+2, confirming the result.',
        'The power rule excludes x⁻¹; its antiderivative is ln|x|+C on intervals away from 0.',
        ['原函数是求导的逆过程。', '对 xⁿ 且 n≠−1，指数加一，再除以新指数。', '加上常数 C，最后求导检查。'],
        '∫(3x²+2) dx = x³+2x+C。对结果求导重新得到 3x²+2，说明计算正确。',
        '幂函数积分公式不适用于 x⁻¹；远离 0 的区间上其原函数为 ln|x|+C。'),
    'calc_definite_integrals': (
        ['A definite integral accumulates signed contributions over an interval.', 'Approximate it with sums of height times width, or use an antiderivative.', 'Regions below the axis contribute negatively; distinguish signed accumulation from geometric area.'],
        '∫₀² x dx = [x²/2]₀² = 2. In contrast, ∫₋₁¹ x dx=0 because the negative and positive contributions cancel.',
        'A zero integral does not imply there is no area between the graph and the axis.',
        ['定积分是在一个区间内累积有符号的贡献。', '可以用高乘宽的和近似，也可以用原函数求值。', '横轴以下贡献为负，要区分净累积与几何面积。'],
        '∫₀² x dx = [x²/2]₀² = 2。而 ∫₋₁¹ x dx=0，因为两侧的正负贡献抵消。',
        '积分为零不代表图像与横轴之间没有面积。'),
    'calc_fundamental_theorem': (
        ['For continuous f, the derivative of ∫ₐˣ f(t)dt is f(x).', 'When the upper endpoint is g(x), multiply f(g(x)) by g′(x).', 'For numerical bounds, evaluate an antiderivative as F(b)−F(a).'],
        'If G(x)=∫₀ˣ² cos(t)dt, then G′(x)=cos(x²)·2x. For a numerical integral, ∫₀¹ 2t dt=[t²]₀¹=1.',
        'Do not forget the chain rule when the endpoint is a function of x.',
        ['f 连续时，∫ₐˣ f(t)dt 对 x 的导数就是 f(x)。', '上限若为 g(x)，结果还要乘以 g′(x)。', '上下限都是数值时，用原函数的 F(b)−F(a) 求定积分。'],
        '若 G(x)=∫₀ˣ² cos(t)dt，则 G′(x)=cos(x²)·2x。数值积分 ∫₀¹ 2t dt=[t²]₀¹=1。',
        '积分上限是复合函数时，不要漏掉链式法则。'),
}


def calculus_lesson(topic_id, chinese=False):
    lesson = LESSONS.get(topic_id)
    if lesson is None:
        return None
    return lesson[3:] if chinese else lesson[:3]
