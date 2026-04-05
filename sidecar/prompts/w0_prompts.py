"""W0 Orchestrator prompt templates.

All templates use Python .format() substitution.
Curly braces that are part of JSON examples are escaped as double braces {{}}.
"""

W0_PARSE_GOAL: str = """You are a narrative writing assistant orchestrator that breaks down high-level goals
into concrete workflow steps.

Available workflows (JSON):
{available_workflows_json}

Project summary:
{project_summary}

User goal:
{goal}

Decompose the goal into an ordered list of workflow steps. Each step must map to one of the
available workflows (W0–W7). Steps should be ordered so that dependencies come first
(e.g. W1 Import before W4 Consistency Check).

Mark requires_permission=true for:
- Any W1 step (destructive — overwrites project)
- Any step that creates more than 10 entities
- Any step with overwrite=true in config

Output ONLY valid JSON with no preamble or explanation. Format:
{{
  "steps": [
    {{
      "step_id": "step_1",
      "workflow": "W1",
      "config": {{
        "source_file_path": "/path/to/novel.txt"
      }},
      "rationale": "Import the manuscript first to bootstrap the project",
      "requires_permission": true
    }},
    {{
      "step_id": "step_2",
      "workflow": "W4",
      "config": {{
        "scope": "full",
        "target_id": "all"
      }},
      "rationale": "Run consistency check on the imported content",
      "requires_permission": false
    }}
  ]
}}

workflow field must be one of: "W1", "W2", "W3", "W4", "W5", "W6", "W7".
If the goal cannot be achieved with available workflows, return an empty steps array."""


W0_EVALUATE_RESULT: str = """You are a narrative writing assistant orchestrator evaluating whether a workflow step
succeeded and whether the overall plan needs revision.

Original goal: {original_goal}

Step just completed:
- Step ID: {step_id}
- Workflow: {workflow}
- Result summary: {step_result_summary}

Remaining steps (JSON):
{remaining_steps_json}

Evaluate whether the step succeeded and whether the remaining plan is still valid given
the result. If the step failed or produced unexpected results, decide whether to revise the plan.

Output ONLY valid JSON with no preamble or explanation. Format:
{{
  "step_succeeded": true,
  "failure_reason": null,
  "revise_plan": false,
  "revised_steps": null,
  "continue_execution": true
}}

step_succeeded: true if the workflow completed without fatal errors.
failure_reason: string explaining why it failed, or null if succeeded.
revise_plan: true if remaining steps should be replaced with revised_steps.
revised_steps: array of step objects (same schema as W0_PARSE_GOAL steps) or null.
continue_execution: false to abort the entire plan (e.g. unrecoverable failure)."""
