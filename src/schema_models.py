from pydantic import BaseModel, Field

LIST_FIELDS = {"main_actors", "causal_chain", "missing_information_a_reporter_might_seek"}

class SchemaCard(BaseModel):
    headline: str = Field(description="The headline or best short title for the article.")
    topic: str = Field(description="Surface topic, such as politics, health, economy, disaster, law, sports.")
    story_type: str = Field(description="A short label for the narrative type of this story.")
    trigger_event: str = Field(description="The event or change that makes the story newsworthy.")
    central_conflict: str = Field(description="The main tension, disagreement, problem, or accountability issue.")
    main_actors: list[str] = Field(description="Important people, groups, institutions, or stakeholders.")
    affected_group: str = Field(description="Who is most directly affected.")
    stakes: str = Field(description="Why the story matters.")
    causal_chain: list[str] = Field(description="A step-by-step chain of causes, effects, or developments.")
    narrative_schema: str = Field(description="The deeper reusable story structure, ignoring surface topic.")
    analogy_signature: str = Field(description="A compact phrase useful for finding structurally similar stories.")
    missing_information_a_reporter_might_seek: list[str] = Field(description="Reporting questions or missing evidence a journalist might pursue.")

class TextFieldFix(BaseModel):
    value: str = Field(description="The corrected/improved value for the field, grounded in the article.")

class ListFieldFix(BaseModel):
    values: list[str] = Field(description="The corrected/improved list of values for the field, grounded in the article.")

class CritiqueIssue(BaseModel):
    field: str = Field(description="The SchemaCard field this issue concerns, e.g. 'central_conflict'.")
    severity: str = Field(description="One of: low, medium, high.")
    issue: str = Field(description="What is vague, unsupported by the article, or missing.")
    suggestion: str = Field(description="A concrete instruction for how to fix this field.")

class SchemaCritique(BaseModel):
    overall_assessment: str = Field(description="A one to two sentence summary of the schema's faithfulness to the article.")
    issues: list[CritiqueIssue] = Field(description="Specific issues found, most important first. Empty if the schema holds up well.")

class DebateResponse(BaseModel):
    advocate: str = Field(description="An answer defending/supporting the article's framing and central actors, grounded in the article's facts.")
    skeptic: str = Field(description="An answer challenging that framing and raising doubts a critical editor would raise, grounded in the article's facts.")