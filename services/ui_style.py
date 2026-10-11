import streamlit as st


def apply_app_styles() -> None:
    """Apply shared presentation styles without changing page behavior."""
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
            background: linear-gradient(135deg, #F6F9FE 0%, #FBFCFF 65%, #F0F5FD 100%);
            color: var(--exam-ink);
        }

        [data-testid="stHeader"] {
            background: rgba(248, 250, 254, 0.95);
        }

        [data-testid="stMainBlockContainer"] {
            max-width: 1320px;
            padding-top: 1.4rem;
            padding-bottom: 3rem;
        }

        h1, h2, h3, h4, p, label, li {
            color: var(--exam-ink);
        }

        [data-testid="stMain"] [data-testid="stMarkdownContainer"] h1 {
            font-size: clamp(2.5rem, 3.8vw, 3.2rem);
            font-weight: 750;
            line-height: 1.16;
            letter-spacing: -0.035em;
        }

        [data-testid="stMain"] [data-testid="stMarkdownContainer"] h2 {
            font-size: 1.9rem;
            font-weight: 700;
            line-height: 1.3;
            letter-spacing: -0.02em;
        }

        [data-testid="stMain"] [data-testid="stMarkdownContainer"] h3 {
            font-size: 1.6rem;
            font-weight: 680;
            line-height: 1.35;
            letter-spacing: -0.015em;
        }

        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li {
            font-size: 1rem;
            line-height: 1.6;
        }

        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] p {
            color: var(--exam-muted) !important;
            font-size: 0.875rem;
            line-height: 1.5;
        }

        [data-testid="stSidebar"] {
            background: #F0F5FD;
            border-right: 1px solid var(--exam-border);
        }

        [data-testid="stSidebar"] [data-testid="stText"] {
            white-space: pre-wrap;
            overflow-wrap: anywhere;
        }

        [data-testid="stSidebarNav"] {
            position: relative;
            padding-top: 0.8rem;
        }

        [data-testid="stSidebarNav"]::before {
            content: "🎓  ExamPilot";
            display: block;
            padding: 0.45rem 0.8rem 1.1rem;
            margin: 0 0.65rem 0.5rem;
            border-bottom: 1px solid var(--exam-border);
            color: var(--exam-ink);
            font-size: 1.45rem;
            font-weight: 750;
            letter-spacing: -0.03em;
        }

        [data-testid="stSidebarNav"] a {
            min-height: 2.8rem;
            margin: 0.15rem 0.55rem;
            border-radius: 0.65rem;
            color: #304461;
            font-size: 1rem;
            font-weight: 550;
        }

        [data-testid="stSidebarNav"] a [data-testid="stIconMaterial"] {
            font-size: 1.3rem !important;
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

        /* These Streamlit button kinds also cover form submits and downloads. */
        button:is(
            [data-testid="stBaseButton-primary"],
            [data-testid="stBaseButton-secondary"],
            [data-testid="stBaseButton-primaryFormSubmit"],
            [data-testid="stBaseButton-secondaryFormSubmit"]
        ) {
            min-height: 2.75rem;
            padding: 0.55rem 1rem;
            border-radius: 0.65rem;
            font-weight: 650;
            transition: background-color 120ms ease, border-color 120ms ease;
        }

        button:is(
            [data-testid="stBaseButton-primary"],
            [data-testid="stBaseButton-primaryFormSubmit"]
        ) {
            border: 1px solid var(--exam-blue);
            background: var(--exam-blue);
            color: #FFFFFF;
        }

        button:is(
            [data-testid="stBaseButton-secondary"],
            [data-testid="stBaseButton-secondaryFormSubmit"]
        ) {
            border: 1px solid #C8D6E9;
            background: #FFFFFF;
            color: #24466F;
        }

        button:is(
            [data-testid="stBaseButton-primary"],
            [data-testid="stBaseButton-secondary"],
            [data-testid="stBaseButton-primaryFormSubmit"],
            [data-testid="stBaseButton-secondaryFormSubmit"]
        ) :is(p, span) {
            color: inherit !important;
            font-size: 0.95rem;
        }

        button:is(
            [data-testid="stBaseButton-primary"],
            [data-testid="stBaseButton-primaryFormSubmit"]
        ):not(:disabled):hover {
            border-color: var(--exam-blue-dark);
            background: var(--exam-blue-dark);
            color: #FFFFFF;
        }

        button:is(
            [data-testid="stBaseButton-secondary"],
            [data-testid="stBaseButton-secondaryFormSubmit"]
        ):not(:disabled):hover {
            border-color: #7FA5DD;
            background: #EDF4FF;
            color: #174FAF;
        }

        button[data-testid^="stBaseButton-"]:focus-visible,
        [data-testid="stSidebarNav"] a:focus-visible,
        [data-testid="stPageLink"] a:focus-visible {
            outline: 3px solid #8CB4ED;
            outline-offset: 2px;
        }

        button:is(
            [data-testid="stBaseButton-primary"],
            [data-testid="stBaseButton-secondary"],
            [data-testid="stBaseButton-primaryFormSubmit"],
            [data-testid="stBaseButton-secondaryFormSubmit"]
        ):disabled {
            border-color: #D2DBE8;
            background: #E9EEF5;
            color: #526581;
            opacity: 1;
        }

        [class*="st-key-dashboard_courses_header"] [data-testid="stHorizontalBlock"] {
            flex-direction: row;
            flex-wrap: nowrap;
            align-items: center;
        }

        [class*="st-key-dashboard_courses_header"] [data-testid="stColumn"] {
            flex: 1 1 0 !important;
            min-width: 0;
            width: auto !important;
        }

        [data-testid="stMain"] [class*="st-key-dashboard_courses_header"]
        [data-testid="stMarkdownContainer"] h3 {
            margin: 0;
            padding: 0 0 0 0.75rem;
            border-left: 4px solid var(--exam-blue);
            color: var(--exam-ink);
            font-size: 2.125rem;
            font-weight: 800;
            line-height: 1.2;
            letter-spacing: -0.035em;
            white-space: nowrap;
        }

        [class*="st-key-dashboard_courses_header"] [data-testid="stMarkdownContainer"] {
            margin-bottom: 0;
        }

        div[class*="st-key-create_course_button"] {
            width: min(100%, 14rem) !important;
            margin-left: auto;
        }

        div[class*="st-key-create_course_button"] button {
            position: relative;
            width: 100% !important;
            max-width: 14rem !important;
            min-height: 3rem !important;
            justify-content: center !important;
            padding: 0.65rem 1rem !important;
        }

        div[class*="st-key-create_course_button"] button > div,
        div[class*="st-key-create_course_button"] button > div > span {
            justify-content: center !important;
        }

        div[class*="st-key-create_course_button"] [data-testid="stIconMaterial"] {
            font-size: 1.65rem !important;
        }

        div[class*="st-key-create_course_button"] button p {
            font-size: 1.05rem;
            font-weight: 650;
        }

        div[class*="st-key-create_course_button"] button > div > span {
            gap: 0.65rem !important;
        }

        [data-testid="stVerticalBlockBorderWrapper"],
        [data-testid="stVerticalBlock"][style*="border:"],
        [data-testid="stVerticalBlock"]:is(
            [class*="st-key-dashboard_course_card_"],
            [class*="st-key-dashboard_course_setup"],
            [class*="st-key-study_scope_panel"],
            [class*="st-key-study_topic_"],
            [class*="st-key-practice_settings_panel"],
            [class*="st-key-practice_overview"],
            [class*="st-key-practice_question_"],
            [class*="st-key-practice_review_"],
            [class*="st-key-practice_submit_panel"],
            [class*="st-key-progress_topic_"],
            [class*="st-key-graph_mode_panel"],
            [class*="st-key-knowledge_graph_canvas"],
            [class*="st-key-knowledge_graph_details"],
            [class*="st-key-anki_export_settings"],
            [class*="st-key-anki_export_summary"],
            [class*="st-key-anki_study_card_"]
        ) {
            border-color: var(--exam-border) !important;
            border-radius: 0.9rem !important;
            background: var(--exam-panel);
            box-shadow: 0 3px 14px rgba(20, 55, 105, 0.04);
        }

        [class*="st-key-knowledge_topic_heading"] {
            padding: 0.85rem 1rem;
            border-left: 4px solid var(--exam-blue);
            border-radius: 0.75rem;
            background: #EFF6FF;
        }

        [class*="st-key-knowledge_topic_stats"] [data-testid="stMetricValue"] {
            font-size: 2.2rem;
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
            font-size: 1.65rem;
            line-height: 1.35;
            overflow-wrap: anywhere;
        }

        [class*="st-key-practice_question_"] [data-testid="stMarkdownContainer"] h3,
        [class*="st-key-practice_review_"] [data-testid="stMarkdownContainer"] h3 {
            font-size: 1.55rem;
            line-height: 1.4;
            margin-bottom: 0.35rem;
        }

        [class*="st-key-practice_question_"] [data-testid="stCaptionContainer"] p,
        [class*="st-key-practice_review_"] [data-testid="stCaptionContainer"] p {
            font-size: 1.05rem;
            font-weight: 700;
            color: var(--exam-ink) !important;
        }

        [class*="st-key-practice_count_"] {
            width: min(100%, 18rem) !important;
        }

        [data-testid="stMetric"] {
            padding: 0.25rem 0.1rem;
        }

        [data-testid="stMetricLabel"] p {
            color: var(--exam-muted) !important;
            font-size: 1rem;
        }

        [data-testid="stMetricValue"] {
            color: var(--exam-ink);
            font-weight: 750;
            font-size: 2.75rem;
        }

        [data-testid="stMetricValue"] > div,
        [data-testid="stMain"] [data-testid="stMetricValue"] [data-testid="stMarkdownContainer"] p {
            font-size: inherit;
            font-weight: inherit;
            line-height: 1.2;
        }

        [class*="st-key-progress_topic_"] [data-testid="stMetricLabel"] p {
            font-size: 0.95rem;
        }

        [class*="st-key-progress_overview"] [data-testid="stMetricLabel"] p {
            font-size: 0.95rem;
        }

        [class*="st-key-progress_overview"] [data-testid="stMetricValue"],
        [class*="st-key-progress_topic_"] [data-testid="stMetricValue"] {
            font-size: 2.5rem;
        }

        [class*="st-key-progress_topic_"] [data-testid="stCaptionContainer"],
        [class*="st-key-progress_topic_"] [data-testid="stCaptionContainer"] p {
            font-size: 0.9rem;
        }

        [data-testid="stWidgetLabel"] p,
        [data-testid="stRadio"] label p,
        [data-testid="stCheckbox"] label p {
            font-size: 0.95rem;
            line-height: 1.45;
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
            gap: 1rem;
        }

        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            min-width: 0;
        }

        [class*="st-key-dashboard_course_card_"] {
            height: 100%;
        }

        [class*="st-key-dashboard_course_card_"] [data-testid="stMarkdownContainer"] h3 {
            font-size: 1.9rem;
            line-height: 1.25;
            overflow-wrap: anywhere;
        }

        [class*="st-key-study_plan_overview"] [data-testid="stMarkdownContainer"] h3,
        [class*="st-key-progress_course_heading"] [data-testid="stMarkdownContainer"] h3 {
            font-size: 1.9rem;
            line-height: 1.25;
            overflow-wrap: anywhere;
        }

        div[class*="st-key-remove_course_"] button {
            min-width: 2.75rem !important;
            padding: 0.5rem !important;
            border-color: transparent !important;
            background: transparent !important;
            color: #61748E !important;
            box-shadow: none !important;
        }

        div[class*="st-key-remove_course_"] button p,
        div[class*="st-key-remove_course_"] button span {
            color: #61748E !important;
        }

        div[class*="st-key-remove_course_"] button:not(:disabled):hover {
            border-color: #F2CECE !important;
            background: #FDECEC !important;
            color: #9E3434 !important;
            box-shadow: none !important;
        }

        div[class*="st-key-remove_course_"] button:hover p,
        div[class*="st-key-remove_course_"] button:hover span {
            color: #9E3434 !important;
        }

        [class*="st-key-confirm_remove_course_"] button:not(:disabled) {
            border-color: #D8A3A3;
            background: #FFFFFF;
            color: #9E3434;
        }

        [class*="st-key-confirm_remove_course_"] button:not(:disabled):hover {
            border-color: #9E3434;
            background: #FDECEC;
            color: #8A2424;
        }

        [data-testid="stForm"] {
            border-color: var(--exam-border);
            border-radius: 0.9rem;
            background: var(--exam-panel);
        }

        [data-testid="stTextInput"] [data-baseweb="input"],
        [data-testid="stNumberInput"] [data-baseweb="input"],
        [data-testid="stTextArea"] textarea,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
            border-color: #C8D6E9;
            border-radius: 0.6rem;
            background: #FFFFFF;
            color: var(--exam-ink);
        }

        [data-testid="stTextInput"] input::placeholder,
        [data-testid="stTextArea"] textarea::placeholder {
            color: #657892;
        }

        [data-testid="stTextInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stNumberInput"] [data-baseweb="input"]:focus-within,
        [data-testid="stTextArea"] textarea:focus-visible {
            border-color: var(--exam-blue);
            box-shadow: 0 0 0 2px #DCEAFF;
        }

        [data-testid="stFileUploaderDropzone"] {
            border: 1px dashed #9BB6DC;
            border-radius: 0.8rem;
            background: #F5F8FD;
            padding: 1.15rem;
        }

        [data-testid="stFileUploaderDropzone"]:focus-within {
            border-color: var(--exam-blue);
        }

        [data-testid="stTabs"] [role="tablist"] {
            gap: 0.8rem;
            border-bottom-color: var(--exam-border);
        }

        [data-testid="stTabs"] [role="tab"] {
            padding: 0.65rem 0.35rem;
            min-height: 2.75rem;
        }

        [data-testid="stTabs"] [role="tab"][aria-selected="true"] p {
            color: var(--exam-blue);
            font-weight: 650;
        }

        .exam-hero {
            position: relative;
            overflow: hidden;
            display: flex;
            min-height: clamp(11rem, 18vw, 15rem);
            flex-direction: column;
            justify-content: center;
            margin: 0 0 0.9rem;
            padding: clamp(1.4rem, 2.8vw, 2.4rem);
            border: 1px solid var(--exam-border);
            border-radius: 1rem;
            background: linear-gradient(105deg, #FFFFFF 0%, #F7FAFF 58%, #EAF3FF 100%);
            isolation: isolate;
        }

        .exam-hero::after {
            position: absolute;
            z-index: -1;
            inset: 0 0 0 auto;
            width: 56%;
            background-image:
                linear-gradient(90deg, #FAFCFF 0%, rgba(250, 252, 255, 0.4) 38%, transparent 70%),
                var(--campus-art);
            background-position: center, center right;
            background-repeat: no-repeat;
            background-size: 100% 100%, cover;
            content: "";
            opacity: 0.8;
        }

        [data-testid="stMain"] .exam-hero h1 {
            position: relative;
            z-index: 1;
            max-width: 38rem;
            margin: 0;
            color: var(--exam-ink);
            font-size: clamp(2.1rem, 3.4vw, 3rem);
            line-height: 1.12;
            letter-spacing: -0.04em;
        }

        .exam-hero h1 span:not([id]):not([data-testid]) {
            color: var(--exam-blue);
        }

        .exam-hero p {
            position: relative;
            z-index: 1;
            max-width: 35rem;
            margin: 0.75rem 0 0;
            color: var(--exam-muted);
            font-size: 1rem;
        }

        .exam-eyebrow {
            color: var(--exam-blue);
            font-size: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        @media (max-width: 768px) {
            [data-testid="stMainBlockContainer"] {
                padding: 1rem 1.1rem 2rem;
            }

            [data-testid="stHorizontalBlock"]:has(
                > [data-testid="stColumn"] [class*="st-key-dashboard_course_card_"]
            ),
            [class*="st-key-knowledge_graph_layout"] > [data-testid="stHorizontalBlock"],
            [class*="st-key-practice_settings_panel"] > [data-testid="stHorizontalBlock"],
            [class*="st-key-anki_export_settings"] > [data-testid="stHorizontalBlock"],
            [class*="st-key-anki_export_summary"] > [data-testid="stHorizontalBlock"],
            [class*="st-key-graph_controls_panel"] > [data-testid="stHorizontalBlock"],
            [data-testid="stVerticalBlock"]:is(
                [class*="st-key-knowledge_graph_layout"],
                [class*="st-key-graph_controls_panel"],
                [class*="st-key-practice_settings_panel"],
                [class*="st-key-anki_export_settings"],
                [class*="st-key-anki_export_summary"]
            ) > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {
                flex-direction: column;
                gap: 0.9rem;
            }

            [data-testid="stHorizontalBlock"]:has(
                > [data-testid="stColumn"] [class*="st-key-dashboard_course_card_"]
            ) > [data-testid="stColumn"],
            [class*="st-key-knowledge_graph_layout"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
            [class*="st-key-practice_settings_panel"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
            [class*="st-key-anki_export_settings"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
            [class*="st-key-anki_export_summary"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
            [class*="st-key-graph_controls_panel"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
            [data-testid="stVerticalBlock"]:is(
                [class*="st-key-knowledge_graph_layout"],
                [class*="st-key-graph_controls_panel"],
                [class*="st-key-practice_settings_panel"],
                [class*="st-key-anki_export_settings"],
                [class*="st-key-anki_export_summary"]
            ) > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
                flex: 1 1 100% !important;
                width: 100% !important;
            }

            [class*="st-key-dashboard_course_card_"] [data-testid="stHorizontalBlock"],
            [class*="st-key-knowledge_graph_canvas"] [data-testid="stHorizontalBlock"],
            [class*="st-key-study_topic_"] [data-testid="stHorizontalBlock"] {
                flex-direction: row;
                gap: 0.6rem;
            }

            [class*="st-key-study_topic_"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {
                flex: 0 0 2rem !important;
                width: 2rem !important;
            }

            [class*="st-key-study_topic_"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {
                flex: 1 1 0 !important;
                width: auto !important;
            }

            .exam-hero {
                min-height: 11rem;
                padding: 1.6rem;
            }

            .exam-hero::after {
                width: 48%;
                opacity: 0.45;
            }

            .exam-hero p {
                max-width: 24rem;
            }

            div[class*="st-key-create_course_button"] button {
                min-height: 2.75rem !important;
                padding: 0.6rem 0.5rem !important;
            }

            div[class*="st-key-create_course_button"] [data-testid="stIconMaterial"] {
                font-size: 1.3rem !important;
            }

            div[class*="st-key-create_course_button"] button p {
                font-size: 0.9rem;
                white-space: nowrap;
            }

            [class*="st-key-dashboard_courses_header"] [data-testid="stHorizontalBlock"] {
                gap: 0.6rem;
            }

            div[class*="st-key-create_course_button"] button > div > span {
                gap: 0.4rem !important;
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

            [class*="st-key-progress_topic_"] > [data-testid="stHorizontalBlock"],
            [class*="st-key-progress_overview"] > [data-testid="stHorizontalBlock"],
            [class*="st-key-practice_result_overview"] > [data-testid="stHorizontalBlock"],
            [data-testid="stVerticalBlock"]:is(
                [class*="st-key-practice_overview"],
                [class*="st-key-progress_topic_"],
                [class*="st-key-progress_overview"],
                [class*="st-key-practice_result_overview"]
            ) > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
                gap: 0.5rem 0.8rem;
            }

            [class*="st-key-progress_topic_"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
            [class*="st-key-progress_overview"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
            [class*="st-key-practice_result_overview"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
            [data-testid="stVerticalBlock"]:is(
                [class*="st-key-practice_overview"],
                [class*="st-key-progress_topic_"],
                [class*="st-key-progress_overview"],
                [class*="st-key-practice_result_overview"]
            ) > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
                flex: 1 1 calc(50% - 0.8rem) !important;
                width: calc(50% - 0.8rem) !important;
            }

        }

        @media (max-width: 480px) {
            [data-testid="stMainBlockContainer"] {
                padding: 0.9rem 0.8rem 1.8rem;
            }

            [data-testid="stMain"] [data-testid="stMarkdownContainer"] h1 { font-size: 2.2rem; }
            [data-testid="stMain"] [data-testid="stMarkdownContainer"] h2 { font-size: 1.7rem; }
            [data-testid="stMain"] [data-testid="stMarkdownContainer"] h3 { font-size: 1.5rem; }

            [data-testid="stMain"] [class*="st-key-dashboard_courses_header"]
            [data-testid="stMarkdownContainer"] h3 {
                padding-left: 0.5rem;
                font-size: clamp(1.55rem, 6.7vw, 1.75rem);
            }

            [class*="st-key-dashboard_course_card_"] [data-testid="stMarkdownContainer"] h3,
            [class*="st-key-study_plan_overview"] [data-testid="stMarkdownContainer"] h3,
            [class*="st-key-progress_course_heading"] [data-testid="stMarkdownContainer"] h3 {
                font-size: 1.7rem;
            }

            .exam-hero {
                min-height: 0;
                padding: 1.3rem 1.1rem;
            }

            [data-testid="stMain"] .exam-hero h1 { font-size: 2rem; }
            .exam-hero::after { width: 100%; opacity: 0.16; }

            [data-testid="stFileUploaderDropzone"] {
                padding: 0.85rem;
                flex-wrap: wrap;
                gap: 0.6rem;
            }

            [data-testid="stTabs"] [role="tablist"] { gap: 0.6rem; }
            [data-testid="stMetricValue"] { font-size: 2.35rem; }

            [class*="st-key-graph_controls_panel"] > [data-testid="stHorizontalBlock"] {
                flex-direction: column;
            }

            [class*="st-key-graph_controls_panel"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
                flex: 1 1 100% !important;
                width: 100% !important;
            }
        }

        [data-testid="stSidebarContent"] {
            display: flex;
            flex-direction: column;
            min-height: 100dvh;
        }

        [data-testid="stSidebarUserContent"] {
            flex: 1;
            display: flex;
            flex-direction: column;
            padding-bottom: 1.25rem;
        }

        [data-testid="stSidebarUserContent"] > div {
            flex: 1;
            display: flex;
            flex-direction: column;
        }

        [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {
            flex: 1;
        }

        [data-testid="stSidebarUserContent"] [data-testid="stLayoutWrapper"]:has(> .st-key-account_sidebar) {
            order: 999;
            margin-top: auto;
        }

        .st-key-account_sidebar {
            padding-top: 1rem;
            border-top: 1px solid var(--exam-border);
        }

        .account-sidebar-identity {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.35rem 0.1rem 0.65rem;
        }

        .account-avatar {
            width: 44px;
            height: 44px;
            flex-shrink: 0;
            border-radius: 50%;
            object-fit: cover;
            border: 2px solid #D9E7FB;
        }

        .account-avatar-initial {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #E1ECFF;
            color: #184FAE;
            font-size: 1.35rem;
            font-weight: 750;
        }

        .account-avatar-large {
            width: 96px;
            height: 96px;
            font-size: 2.5rem;
            margin-bottom: 0.75rem;
        }

        .account-sidebar-copy {
            display: flex;
            flex-direction: column;
            min-width: 0;
        }

        .account-sidebar-label {
            font-size: 0.7rem;
            letter-spacing: 0.075em;
            color: var(--exam-muted);
        }

        .account-sidebar-copy strong {
            font-size: 1.05rem;
            line-height: 1.4;
            overflow-wrap: anywhere;
        }

        .st-key-account_sidebar [data-testid="stPageLink"] {
            border-radius: 0.65rem;
            background: #E8F0FE;
        }

        .st-key-account_sidebar button,
        .st-key-account_sidebar [data-testid="stPageLink"] a {
            min-height: 44px;
        }

        .st-key-account_identity,
        .st-key-account_avatar_controls {
            padding: 1.2rem;
        }

        @media (max-width: 640px) {
            [data-testid="stHorizontalBlock"]:has(.st-key-account_identity) {
                flex-direction: column;
            }

            [data-testid="stHorizontalBlock"]:has(.st-key-account_identity) > [data-testid="stColumn"] {
                width: 100% !important;
                flex: 1 1 100% !important;
            }
        }

        @media (prefers-reduced-motion: reduce) {
            button[data-testid^="stBaseButton-"] { transition: none; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
