# Debug Session: Locomo Choices Parsing

**Issue**: `locomo.py` hardcodes `choices=[]` and `answer_idx=-1` instead of extracting them from the 'qa' dictionary in the JSON data.

## Root Cause
In `evaluation/datasets/locomo.py`, the `_load_from_github` data parsing loops over `qa_list` but just populates empty arrays and -1 for the choices and answers:

```python
            # Build questions from QA annotations
            questions = []
            qa_list = sample.get("qa", [])
            for qa in qa_list:
                question = LocomoQuestion(
                    question=qa.get("question", ""),
                    choices=[],
                    answer_idx=-1,
                    reasoning_type=qa.get("category", "")
                )
                questions.append(question)
```

We need to inspect the LoCoMo data format to see where choices and correct answers are stored.

If we look at `qa` objects in `locomo10.json`, they probably have fields like `choices` and `answer` (or `correct_answer`). We need to read those fields.
