from pydantic import BaseModel, Field

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