from enum import Enum

class QualityRubric(Enum):
    STYLE_CONSISTENCY = "Style Consistency (风格一致性)"
    EMOTIONAL_INTELLIGENCE = "Emotional Intelligence (情商/共情)"
    IMMERSION = "Immersion (沉浸感/去AI味)"
    
    @staticmethod
    def get_description(rubric):
        descriptions = {
            QualityRubric.STYLE_CONSISTENCY: "回复是否完全符合人设的语气、口癖和性格特征？",
            QualityRubric.EMOTIONAL_INTELLIGENCE: "回复是否敏锐地捕捉到了用户的情绪，并给出了恰当的反应（安慰、共鸣或挑逗）？",
            QualityRubric.IMMERSION: "回复是否像真人一样自然？是否避免了'作为AI'、'我建议'等典型的机器味？"
        }
        return descriptions.get(rubric, "")

    @staticmethod
    def get_all_descriptions():
        return "\n".join([f"- {r.value}: {QualityRubric.get_description(r)}" for r in QualityRubric])
