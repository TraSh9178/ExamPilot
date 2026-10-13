"""Local course illustrations with a neutral fallback for other subjects."""


def course_icon_svg(course_id: str, course_name: str) -> str:
    name = (course_id + " " + course_name).casefold()
    if any(word in name for word in ("python", "programming", "computer", "coding", "计算机", "编程")):
        art = '<path d="M28 25 13 40l15 15m24-30 15 15-15 15M45 19 35 61"/>'
    elif any(word in name for word in ("econ", "finance", "business", "经济", "金融")):
        art = '<path d="M14 15v51h52M21 53l15-16 12 8 17-25M53 20h12v12"/><path d="M24 66V55m15 11V47m15 19V43"/>'
    elif any(word in name for word in ("calculus", "math", "algebra", "微积分", "数学", "代数")):
        art = '<path d="M12 62H70M23 72V10"/><path d="M13 60C36 79 39 12 56 24c6 4 9 12 13 17"/>'
    else:
        art = '<path d="M40 23c-9-8-20-8-29-5v43c10-3 20-2 29 5 9-7 19-8 29-5V18c-9-3-20-3-29 5Zm0 0v43M19 29h12m-12 9h12m18-9h12m-12 9h12"/>'
    return '<svg viewBox="0 0 80 80" fill="none" stroke="#2166DB" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round">' + art + '</svg>'
