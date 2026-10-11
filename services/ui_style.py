import streamlit as st


def apply_app_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            color-scheme: light;
            --exam-blue: #2166DB;
            --exam-blue-dark: #184FAE;
            --exam-ink: #102044;
            --exam-muted: #526581;
            --exam-border: #DCE6F4;
            --exam-panel: #FFFFFF;
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(ellipse at 90% 2%, #E6F1FF 0, transparent 35%),
                linear-gradient(135deg, #F5F9FF 0%, #FFFFFF 58%, #F1F7FF 100%);
            color: var(--exam-ink);
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        [data-testid="stMainBlockContainer"] {
            max-width: 1380px;
            padding-top: 1rem;
            padding-bottom: 3rem;
        }

        h1, h2, h3, h4, p, label, li {
            color: var(--exam-ink);
        }

        h1 {
            font-size: clamp(2.5rem, 4vw, 3.1rem);
            font-weight: 760;
            line-height: 1.08;
            letter-spacing: -0.04em;
        }

        h2 {
            font-size: 1.65rem;
            font-weight: 720;
            line-height: 1.25;
            letter-spacing: -0.025em;
        }

        h3 {
            font-size: 1.35rem;
            font-weight: 700;
            line-height: 1.3;
            letter-spacing: -0.02em;
        }

        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li {
            font-size: 1.0625rem;
            line-height: 1.55;
        }

        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] p {
            color: var(--exam-muted) !important;
            font-size: 0.92rem;
            line-height: 1.45;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #EEF5FF 0%, #F7FAFF 100%);
            border-right: 1px solid var(--exam-border);
        }

        [data-testid="stSidebarNav"] {
            position: relative;
            padding-top: 1.1rem;
        }

        [data-testid="stSidebarNav"]::before {
            content: "🎓  ExamPilot";
            display: block;
            padding: 0.5rem 1rem 1.2rem;
            margin: 0 0.75rem 0.65rem;
            border-bottom: 1px solid var(--exam-border);
            color: var(--exam-ink);
            font-size: 1.75rem;
            font-weight: 800;
            letter-spacing: -0.035em;
        }

        [data-testid="stSidebarNav"] a {
            min-height: 3.5rem;
            margin: 0.25rem 0.55rem;
            border-radius: 0.7rem;
            color: #304461;
            font-size: 1.25rem;
            font-weight: 550;
        }

        [data-testid="stSidebarNav"] a [data-testid="stIconMaterial"] {
            font-size: 1.5rem !important;
        }

        [data-testid="stSidebarNav"] a:hover {
            background: #E2EDFF;
            color: var(--exam-ink);
        }

        [data-testid="stSidebarNav"] a[aria-current="page"] {
            background: #DCEAFF;
            color: #174FAF;
            font-weight: 700;
        }

        [data-testid="stButton"] > button {
            min-height: 3rem;
            border: 1px solid var(--exam-blue) !important;
            border-radius: 0.75rem !important;
            background: var(--exam-blue) !important;
            color: #FFFFFF !important;
            font-weight: 650;
            font-size: 1rem;
            transition: background-color 120ms ease, box-shadow 120ms ease;
        }

        [data-testid="stButton"] > button p,
        [data-testid="stButton"] > button span {
            color: #FFFFFF !important;
            font-size: 1rem;
        }

        .stApp [data-testid="stButton"] > button:not(:disabled):hover {
            border-color: var(--exam-blue-dark) !important;
            background: var(--exam-blue-dark) !important;
            color: #FFFFFF !important;
        }

        [data-testid="stButton"] > button:focus-visible {
            outline: 3px solid #8CB4ED !important;
            outline-offset: 2px;
            box-shadow: 0 0 0 2px #FFFFFF;
        }

        [data-testid="stButton"] > button:disabled {
            border-color: #CBD5E1 !important;
            background: #E2E8F0 !important;
            color: #475569 !important;
            opacity: 1 !important;
        }

        [data-testid="stButton"] > button:disabled p,
        [data-testid="stButton"] > button:disabled span {
            color: #475569 !important;
        }

        div[class*="st-key-create_course_button"] {
            width: min(100%, 34rem) !important;
        }

        div[class*="st-key-create_course_button"] button {
            position: relative;
            width: 100% !important;
            max-width: 34rem !important;
            min-height: 5rem !important;
            justify-content: flex-start !important;
            padding: 0.75rem 1.5rem !important;
            border: 1px solid var(--exam-blue) !important;
            border-radius: 1rem !important;
            background: var(--exam-blue) !important;
            color: #FFFFFF !important;
            box-shadow: 0 3px 12px rgba(30, 76, 130, 0.06);
        }

        div[class*="st-key-create_course_button"] button > div,
        div[class*="st-key-create_course_button"] button > div > span {
            justify-content: flex-start !important;
        }

        div[class*="st-key-create_course_button"] [data-testid="stIconMaterial"] {
            width: 3.1rem !important;
            color: #FFFFFF !important;
            font-size: 2.8rem !important;
        }

        div[class*="st-key-create_course_button"] button p {
            color: #FFFFFF !important;
            font-size: 1.35rem;
            font-weight: 650;
        }

        div[class*="st-key-create_course_button"] button > div > span {
            gap: 0.85rem !important;
        }

        div[class*="st-key-create_course_button"] button:hover {
            border-color: var(--exam-blue-dark) !important;
            background: var(--exam-blue-dark) !important;
            color: #FFFFFF !important;
            box-shadow: 0 5px 18px rgba(30, 76, 130, 0.1);
        }

        div[class*="st-key-create_course_button"] button:hover p,
        div[class*="st-key-create_course_button"] button:focus-visible p {
            color: #FFFFFF !important;
        }

        [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--exam-border) !important;
            border-radius: 1rem !important;
            background: var(--exam-panel);
            box-shadow: 0 5px 18px rgba(20, 55, 105, 0.055);
        }

        [class*="st-key-knowledge_topic_heading"] {
            padding: 0.85rem 1rem;
            border-left: 4px solid var(--exam-blue);
            border-radius: 0.75rem;
            background: #EFF6FF;
        }

        [class*="st-key-study_topic_"]
        [data-testid="stHorizontalBlock"]
        > [data-testid="stColumn"]:first-child
        [data-testid="stMarkdownContainer"] h3:first-of-type {
            color: var(--exam-blue);
        }

        [class*="st-key-knowledge_graph_canvas"] {
            overflow: hidden;
        }

        [class*="st-key-knowledge_graph_canvas"] iframe {
            display: block;
            width: 100%;
            max-width: 100%;
        }

        div[class*="st-key-graph_zoom_out_"] button,
        div[class*="st-key-graph_zoom_in_"] button {
            min-width: 2.5rem;
            padding: 0.35rem;
            font-size: 1.25rem !important;
        }

        [class*="st-key-practice_overview"] [data-testid="stMarkdownContainer"] p {
            font-size: 1.35rem;
            line-height: 1.35;
            overflow-wrap: anywhere;
        }

        [class*="st-key-practice_question_"] [data-testid="stMarkdownContainer"] h3,
        [class*="st-key-practice_review_"] [data-testid="stMarkdownContainer"] h3 {
            font-size: 1.2rem;
            line-height: 1.4;
            margin-bottom: 0.35rem;
        }

        [class*="st-key-practice_count_"] {
            width: min(100%, 18rem) !important;
        }

        [data-testid="stMetric"] {
            padding: 0.25rem 0.1rem;
        }

        [data-testid="stMetricLabel"] p {
            color: var(--exam-muted) !important;
            font-size: 0.92rem;
        }

        [data-testid="stMetricValue"] {
            color: var(--exam-ink);
            font-weight: 750;
        }

        [class*="st-key-progress_topic_"] [data-testid="stMetricLabel"] p {
            font-size: 1.1rem;
        }

        [class*="st-key-progress_overview"] [data-testid="stMetricLabel"] p {
            font-size: 1.1rem;
        }

        [class*="st-key-progress_overview"] [data-testid="stMetricValue"],
        [class*="st-key-progress_topic_"] [data-testid="stMetricValue"] {
            font-size: 1.8rem;
        }

        [class*="st-key-progress_topic_"] [data-testid="stCaptionContainer"],
        [class*="st-key-progress_topic_"] [data-testid="stCaptionContainer"] p {
            font-size: 1.05rem;
        }

        [data-testid="stWidgetLabel"] p,
        [data-testid="stRadio"] label p,
        [data-testid="stCheckbox"] label p {
            font-size: 1rem;
            line-height: 1.4;
        }

        .graph-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem 0.85rem;
            padding: 0.75rem 0 0.15rem;
            border-top: 1px solid var(--exam-border);
            color: var(--exam-muted);
            font-size: 0.9rem;
        }

        .graph-legend span {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
        }

        .graph-legend i {
            width: 0.62rem;
            height: 0.62rem;
            border-radius: 50%;
        }

        [data-testid="stHorizontalBlock"] {
            align-items: stretch;
            gap: 1.1rem;
        }

        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            min-width: 0;
        }

        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]
        > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] {
            display: flex;
            flex: 1 1 auto;
        }

        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]
        > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]
        > [data-testid="stVerticalBlock"] {
            align-items: stretch;
            flex: 1 1 auto;
        }

        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]
        > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]
        > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:last-child {
            margin-top: auto;
        }

        [data-testid="stVerticalBlockBorderWrapper"] {
            height: 100%;
        }

        [data-testid="stSidebarNav"] [data-testid="stPageLink"] {
            width: auto;
        }

        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            display: flex;
            flex-direction: column;
        }

        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {
            width: 100%;
        }

        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"][style*="border"] {
            height: 100%;
        }

        div[class*="st-key-remove_course_"] button {
            min-width: 2.5rem !important;
            padding: 0.35rem !important;
            border-color: transparent !important;
            background: transparent !important;
            color: #74849B !important;
            box-shadow: none !important;
        }

        div[class*="st-key-remove_course_"] button p,
        div[class*="st-key-remove_course_"] button span {
            color: #74849B !important;
        }

        div[class*="st-key-remove_course_"] button [data-testid="stMarkdownContainer"] {
            display: none;
        }

        div[class*="st-key-remove_course_"] button:hover,
        div[class*="st-key-remove_course_"] button:focus-visible {
            border-color: transparent !important;
            background: #FDECEC !important;
            color: #A43F3F !important;
            box-shadow: none !important;
        }

        div[class*="st-key-remove_course_"] button:hover p,
        div[class*="st-key-remove_course_"] button:hover span,
        div[class*="st-key-remove_course_"] button:focus-visible p,
        div[class*="st-key-remove_course_"] button:focus-visible span {
            color: #A43F3F !important;
        }

        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stSelectbox"] [data-baseweb="select"],
        [data-testid="stMultiSelect"] [data-baseweb="select"] {
            border-color: var(--exam-border);
            border-radius: 0.65rem;
            background: #FFFFFF;
            color: var(--exam-ink);
        }

        [data-testid="stTextInput"] input::placeholder {
            color: #71829A;
        }

        [data-testid="stFileUploaderDropzone"] {
            border: 1px dashed #8CB4ED;
            border-radius: 0.9rem;
            background: #F1F7FF;
        }

        [data-testid="stFileUploaderDropzone"] button {
            border: 1px solid var(--exam-blue) !important;
            border-radius: 0.65rem !important;
            background: var(--exam-blue) !important;
            color: #FFFFFF !important;
        }

        [data-testid="stFileUploaderDropzone"] button p {
            color: #FFFFFF !important;
        }

        [data-testid="stExpandSidebarButton"] button {
            border: 1px solid var(--exam-blue) !important;
            background: var(--exam-blue) !important;
            color: #FFFFFF !important;
        }

        [data-testid="stExpandSidebarButton"] button svg {
            fill: currentColor !important;
            color: #FFFFFF !important;
        }

        .exam-hero {
            position: relative;
            overflow: hidden;
            display: flex;
            min-height: clamp(15rem, 22vw, 19rem);
            flex-direction: column;
            justify-content: center;
            margin: 0 0 1.2rem;
            padding: clamp(1.8rem, 3.4vw, 3.4rem);
            border: 0;
            border-radius: 0;
            background: linear-gradient(105deg, #F9FCFF 0%, #F5FAFF 58%, #EAF5FF 100%);
            box-shadow: 0 1px 0 rgba(180, 207, 235, 0.35);
            isolation: isolate;
        }

        .exam-hero::after {
            position: absolute;
            z-index: -1;
            inset: 0 0 0 auto;
            width: 58%;
            background-image:
                linear-gradient(90deg, #F9FCFF 0%, rgba(249, 252, 255, 0.2) 33%, transparent 58%),
                var(--campus-art);
            background-position: center, center right;
            background-repeat: no-repeat;
            background-size: 100% 100%, cover;
            content: "";
            opacity: 0.9;
        }

        .exam-hero h1 {
            position: relative;
            z-index: 1;
            max-width: 680px;
            margin: 0;
            color: var(--exam-ink);
            font-size: clamp(2.7rem, 4.3vw, 3.65rem);
            line-height: 1.04;
            letter-spacing: -0.045em;
        }

        .exam-hero h1 span {
            color: var(--exam-blue);
        }

        .exam-hero p {
            position: relative;
            z-index: 1;
            max-width: 40rem;
            margin: 0.9rem 0 0;
            color: var(--exam-muted);
            font-size: clamp(1rem, 1.35vw, 1.2rem);
        }

        @media (max-width: 640px) {
            [data-testid="stMainBlockContainer"] {
                padding: 0.8rem 1rem 2rem;
            }

            [data-testid="stHorizontalBlock"]:has(
                > [data-testid="stColumn"] [class*="st-key-open_course_"]
            ) {
                flex-direction: column;
                gap: 0.9rem;
            }

            [data-testid="stHorizontalBlock"]:has(
                > [data-testid="stColumn"] [class*="st-key-open_course_"]
            ) > [data-testid="stColumn"] {
                flex: 1 1 100% !important;
                width: 100% !important;
            }

            [data-testid="stHorizontalBlock"]:has(
                > [data-testid="stColumn"] > [data-testid="stVerticalBlock"]
                > [data-testid="stElementContainer"][class*="st-key-remove_course_"]
            ) {
                flex-direction: row !important;
            }

            [data-testid="stHorizontalBlock"]:has(
                > [data-testid="stColumn"] > [data-testid="stVerticalBlock"]
                > [data-testid="stElementContainer"][class*="st-key-open_course_"]
            ) > [data-testid="stColumn"] {
                flex: 1 1 0% !important;
                width: auto !important;
            }

            [data-testid="stHorizontalBlock"]:has(
                > [data-testid="stColumn"] > [data-testid="stVerticalBlock"]
                > [data-testid="stElementContainer"][class*="st-key-remove_course_"]
            ) > [data-testid="stColumn"]:has(
                [class*="st-key-remove_course_"]
            ) {
                flex: 0 0 2.5rem !important;
                width: 2.5rem !important;
            }

            .exam-hero {
                min-height: 0;
                justify-content: flex-start;
                padding: 2.1rem 1.25rem 1.8rem;
                margin-bottom: 1rem;
                background: linear-gradient(180deg, #F9FCFF 0%, #F3F9FF 100%);
            }

            .exam-hero::after {
                inset: auto 0 0;
                width: 100%;
                height: 40%;
                background-image:
                    linear-gradient(180deg, #F9FCFF 0%, rgba(249, 252, 255, 0.7) 58%, transparent 100%),
                    var(--campus-art);
                background-position: center, center 64%;
                opacity: 0.72;
            }

            .exam-hero h1 {
                font-size: clamp(2rem, 10vw, 2.7rem);
            }

            .exam-hero p {
                max-width: 24rem;
            }

            div[class*="st-key-create_course_button"] button {
                min-height: 4.5rem !important;
                padding: 0.65rem 1rem !important;
            }

            div[class*="st-key-create_course_button"] [data-testid="stIconMaterial"] {
                width: 2.75rem !important;
                font-size: 2.4rem !important;
            }

            div[class*="st-key-create_course_button"] button p {
                font-size: 1.2rem;
            }

            [class*="st-key-practice_overview"]
            > [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
                gap: 0.5rem 0.8rem;
            }

            [class*="st-key-practice_overview"]
            > [data-testid="stHorizontalBlock"]
            > [data-testid="stColumn"]:first-child {
                flex: 1 1 100% !important;
                width: 100% !important;
            }

            [class*="st-key-practice_overview"]
            > [data-testid="stHorizontalBlock"]
            > [data-testid="stColumn"]:nth-child(2),
            [class*="st-key-practice_overview"]
            > [data-testid="stHorizontalBlock"]
            > [data-testid="stColumn"]:nth-child(3) {
                flex: 1 1 calc(50% - 0.8rem) !important;
                width: calc(50% - 0.8rem) !important;
            }

            [class*="st-key-progress_topic_"]
            > [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
                gap: 0.5rem 0.8rem;
            }

            [class*="st-key-progress_topic_"]
            > [data-testid="stHorizontalBlock"]
            > [data-testid="stColumn"]:nth-child(1),
            [class*="st-key-progress_topic_"]
            > [data-testid="stHorizontalBlock"]
            > [data-testid="stColumn"]:nth-child(2) {
                flex: 1 1 calc(50% - 0.8rem) !important;
                width: calc(50% - 0.8rem) !important;
            }

            [class*="st-key-progress_topic_"]
            > [data-testid="stVerticalBlock"]
            > [data-testid="stHorizontalBlock"]
            > [data-testid="stColumn"]:nth-child(3) {
                flex: 1 1 100% !important;
                width: 100% !important;
            }

        }
        </style>
        """,
        unsafe_allow_html=True,
    )
