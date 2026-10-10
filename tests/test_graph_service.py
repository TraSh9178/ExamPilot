from models.schemas import TopicStats
from services.graph_service import get_status_by_topic

import pytest

import json

from models.schemas import StudyPackage
import services.graph_service as graph_service
from services.graph_service import build_graph, get_node_color


def test_build_graph_from_sample_course():
    with open("data/sample_course.json", encoding="utf-8") as file:
        data = json.load(file)

    package = StudyPackage.model_validate(data)
    graph = build_graph(package)

    assert len(graph["nodes"]) == 3
    assert len(graph["edges"]) == 2

    node_ids = {node["id"] for node in graph["nodes"]}

    assert node_ids == {
        "supply_demand",
        "elasticity",
        "price_controls",
    }
   
@pytest.mark.parametrize(
    "status, expected_color",
    [
        ("unattempted", "#94A3B8"),
        ("insufficient_evidence", "#A78BFA"),
        ("weak", "#EF4444"),
        ("developing", "#F59E0B"),
        ("mastered", "#22C55E"),
    ],
)
def test_node_colors(status, expected_color):
    assert get_node_color(status) == expected_color
  
def test_invalid_mastery_status():
    with pytest.raises(ValueError, match="Unknown mastery status"):
        get_node_color("unknown")

def test_mock_and_topic_modes_are_separate():
    stats = [
        TopicStats(
            topic_id="t1",
            mode="mock",
            correct=1,
            attempted=4,
            accuracy=25.0,
        ),
        TopicStats(
            topic_id="t1",
            mode="topic",
            correct=4,
            attempted=4,
            accuracy=100.0,
        ),
    ]

    mock_result = get_status_by_topic(stats, "mock")
    topic_result = get_status_by_topic(stats, "topic")

    assert mock_result == {"t1": "weak"}
    assert topic_result == {"t1": "mastered"}

def test_status_by_topic_delegates_to_mastery_engine(monkeypatch):
    stats = [
        TopicStats(
            topic_id="t1",
            mode="mock",
            correct=1,
            attempted=4,
            accuracy=25.0,
        ),
        TopicStats(
            topic_id="t2",
            mode="topic",
            correct=4,
            attempted=4,
            accuracy=100.0,
        ),
    ]
    classified = []

    def classify(item):
        classified.append(item)
        return "developing"

    monkeypatch.setattr(graph_service, "get_mastery_status", classify)

    result = get_status_by_topic(stats, "mock")

    assert result == {"t1": "developing"}
    assert classified == [stats[0]]

def test_duplicate_topic_stats_rejected():
    stats = [
        TopicStats(
            topic_id="t1",
            mode="mock",
            correct=2,
            attempted=3,
            accuracy=66.67,
        ),
        TopicStats(
            topic_id="t1",
            mode="mock",
            correct=3,
            attempted=3,
            accuracy=100.0,
        ),
    ]

    with pytest.raises(ValueError, match="Duplicate topic stats"):
        get_status_by_topic(stats, "mock")