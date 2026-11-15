"""Typeset known course notation without rewriting saved course text or code."""
import re
import streamlit as st

# Literal, reviewed notation from the calculus catalog. Longest matches win;
# existing LaTeX and code spans are kept verbatim rather than parsed again.
NOTATION = {
    'sin(u)/u → 1': r'\frac{\sin u}{u}\to1',
    'sin(3x)/x = 3·sin(3x)/(3x)': r'\frac{\sin(3x)}x=3\frac{\sin(3x)}{3x}',
    '[f(x+h) − f(x)]/h': r'\frac{f(x+h)-f(x)}h',
    '[(x+h)²−x²]/h = 2x+h': r'\frac{(x+h)^2-x^2}h=2x+h',
    '(x² − 4)/(x − 2)': r'\frac{x^2-4}{x-2}',
    '(x²−4)/(x−2)': r'\frac{x^2-4}{x-2}',
    '(x − 2)(x + 2)': r'(x-2)(x+2)',
    '[f(b)−f(a)]/(b−a)': r'\frac{f(b)-f(a)}{b-a}',
    'f′(x)=2x sin(x)+x² cos(x)': r"f'(x)=2x\sin x+x^2\cos x",
    'f′(x)=2x sin(x)+x²cos(x)': r"f'(x)=2x\sin x+x^2\cos x",
    'f(x)=x²sin(x)': r'f(x)=x^2\sin x',
    'y′=24x(3x²+1)³': r"y'=24x(3x^2+1)^3",
    'y=(3x²+1)⁴': r'y=(3x^2+1)^4',
    '4(3x²+1)³': r'4(3x^2+1)^3',
    'x²+y²=25': r'x^2+y^2=25',
    '2x+2y y′=0': r"2x+2yy'=0",
    'y′=−x/y': r"y'=-\frac xy", '2y y′': r"2yy'",
    'dA/dt=2πr·dr/dt': r'\frac{dA}{dt}=2\pi r\frac{dr}{dt}',
    'dA/dt=12π cm²/s': r'\frac{dA}{dt}=12\pi\,\mathrm{cm}^2/\mathrm{s}',
    'dr/dt=2 cm/s': r'\frac{dr}{dt}=2\,\mathrm{cm}/\mathrm{s}',
    'A=πr²': r'A=\pi r^2', '12π cm²/s': r'12\pi\,\mathrm{cm}^2/\mathrm{s}',
    '∫(3x²+2) dx = x³+2x+C': r'\int(3x^2+2)\,dx=x^3+2x+C',
    '∫₀² x dx = [x²/2]₀² = 2': r'\int_0^2 x\,dx=\left[\frac{x^2}2\right]_0^2=2',
    '∫₋₁¹ x dx=0': r'\int_{-1}^1x\,dx=0',
    'G(x)=∫₀ˣ² cos(t)dt': r'G(x)=\int_0^{x^2}\cos t\,dt',
    'G′(x)=cos(x²)·2x': r"G'(x)=\cos(x^2)\cdot2x",
    '∫₀¹ 2t dt=[t²]₀¹=1': r'\int_0^1 2t\,dt=[t^2]_0^1=1',
    '∫ₐˣ f(t)dt': r'\int_a^x f(t)\,dt',
    'F(b)−F(a)': r'F(b)-F(a)',
    'f(x)=x²−4x': r'f(x)=x^2-4x', 'f(x)=x³−3x': r'f(x)=x^3-3x',
    'f(x)=x²': r'f(x)=x^2', 'f(x)=x³': r'f(x)=x^3',
    'f′(x)=2x−4': r"f'(x)=2x-4", 'f′(x)=2x': r"f'(x)=2x",
    'f′(c)=2c=4': r"f'(c)=2c=4", 'f′(c)=2c': r"f'(c)=2c",
    'f′=3(x²−1)': r"f'=3(x^2-1)", 'f″=6x': r"f''=6x",
    'f′=0': r"f'=0", 'f″=0': r"f''=0",
    'x³+2x+C': r'x^3+2x+C', '3x²+2': r'3x^2+2',
    '3(x²−1)': r'3(x^2-1)', 'x²+3x → 10': r'x^2+3x\to10',
    '1/(x−2)': r'\frac1{x-2}', '(9−1)/2=4': r'\frac{9-1}2=4',
    'f(0)=0': r'f(0)=0', 'f(2)=−4': r'f(2)=-4', 'f(5)=5': r'f(5)=5',
    'f(2)=k': r'f(2)=k', 'f(2)': r'f(2)',
    'x ≠ 2': r'x\ne2', 'x≠2': r'x\ne2', 'y≠0': r'y\ne0',
    'h ≠ 0': r'h\ne0', 'h → 0': r'h\to0', 'x → 0': r'x\to0',
    'x → 2': r'x\to2', 'x² → 4': r'x^2\to4', '3x → 6': r'3x\to6',
    'n≠−1': r'n\ne-1', 'x⁻¹': r'x^{-1}', 'x³': r'x^3', 'x²': r'x^2',
    'f′(x)': r"f'(x)", 'f′(c)': r"f'(c)", 'y′': r"y'",
    '0/0': r'\frac00', 'x + 2': r'x+2', 'x − 2': r'x-2',
    'lim(x→0) sin(x)/x = 1': r'\lim_{x\to0}\frac{\sin x}{x}=1',
    'lim(x→0) (1 − cos(x))/x = 0': r'\lim_{x\to0}\frac{1-\cos x}{x}=0',
    'f′(c) = [f(b) − f(a)]/(b − a)': r"f'(c)=\frac{f(b)-f(a)}{b-a}",
    '∫ from a to x of f(t) dt': r'\int_a^x f(t)\,dt',
    '∫ from a to b of f(x) dx = F(b) − F(a)': r'\int_a^b f(x)\,dx=F(b)-F(a)',
    'A(x) = ∫ from a to x of f(t) dt': r'A(x)=\int_a^x f(t)\,dt',
    '(u′v − uv′)/v²': r"\frac{u'v-uv'}{v^2}",
    'u′v + uv′': r"u'v+uv'",
    'f′(g(x))': r"f'(g(x))", 'g′(x)': r"g'(x)",
    'f(g(x))': r'f(g(x))',
    'xⁿ⁺¹/(n + 1)': r'\frac{x^{n+1}}{n+1}',
    'n ≠ −1': r'n\ne-1', '1/x': r'\frac1x', 'ln|x|': r'\ln|x|',
    '2y·dy/dx': r'2y\frac{dy}{dx}', 'dy/dx': r'\frac{dy}{dx}',
    'f″ = 0': r"f''=0", 'F′ = f': r"F'=f", 'f′': r"f'", 'f″': r"f''",
    'f(a)': r'f(a)', 'f(x)': r'f(x)', 'xⁿ': r'x^n', 'y²': r'y^2', 'v ≠ 0': r'v\ne0',
    'u/v': r'\frac uv', '|f|': r'|f|',
}
PATTERN = re.compile('|'.join(re.escape(text) for text in sorted(NOTATION, key=len, reverse=True)))


def math_markdown(text):
    # No arbitrary expression evaluation or conversion of user code.
    parts = re.split(r'(\$\$.*?\$\$|\$[^$\n]+\$|```.*?```|`[^`]+`)', text, flags=re.S)
    return ''.join(part if i % 2 else PATTERN.sub(lambda match: '$'+NOTATION[match[0]]+'$', part)
                   for i,part in enumerate(parts))


def write_summary(text):
    formatted = math_markdown(text)
    if formatted == text:
        st.write(text)
    else:
        st.markdown(formatted)
