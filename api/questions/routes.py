# app/api/question_routes.py
from fastapi import APIRouter, Depends, HTTPException, Query
from bson import ObjectId
from db.models.question import Question
from db.models.answer import Answer
from db.models.comment import Comment

from db.models.user import User
from utils.dependencies import verify_in_company
from utils.ai import generate_ai_answer

router = APIRouter(tags=["Questions"])

# Create a Question
@router.post("/questions")
async def create_question(question_data: dict, current_user: User = Depends(verify_in_company)):
    question = Question(
        title=question_data["title"],
        description=question_data["description"],
        tags=question_data.get("tags", []),
        company_id=current_user.company_id,
        user_id=current_user["sub"],
        upvotes=0,
    )
    await question.insert()
    return {"message": "Question created successfully", "question_id": str(question.id)}

# Get Questions (with pagination, filters, and sorting)
@router.get("/questions")
async def get_questions(
    page: int = 1,
    page_size: int = 10,
    tags: list[str] = Query(default=None),
    sort_by: str = Query(default="upvotes"),  # "upvotes" or "created_at"
    current_user: User = Depends(verify_in_company)
):
    query = {}
    if tags:
        query["tags"] = {"$in": tags}
    
    query["company_id"] = current_user.company_id
    questions = (
        Question.find(query)
        .sort(-1 if sort_by == "upvotes" else -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    return await questions.to_list()

# Get Question by ID (with answers and comments)
@router.get("/questions/{question_id}")
async def get_question_by_id(question_id: str, current_user: User = Depends(verify_in_company)):
    question = await Question.get(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    if question.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    answers = await Answer.find(Answer.question_id == question_id).to_list()
    for answer in answers:
        answer.comments = await Comment.find(Comment.answer_id == answer.id).to_list()

    return {"question": question, "answers": answers}

# Answer a Question
@router.post("/questions/{question_id}/answers")
async def answer_question(question_id: str, answer_data: dict, current_user: User = Depends(verify_in_company)):
    question = await Question.get(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    answer = Answer(
        question_id=question_id,
        answer=answer_data["answer"],
        user_id=current_user["sub"],
        upvotes=0,
        is_ai=False,
    )
    await answer.insert()
    return {"message": "Answer added successfully"}

# Comment on an Answer
@router.post("/answers/{answer_id}/comments")
async def comment_on_answer(answer_id: str, comment_data: dict, current_user: User = Depends(verify_in_company)):
    answer = await Answer.get(answer_id)
    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    comment = Comment(
        answer_id=answer_id,
        comment=comment_data["comment"],
        user_id=current_user["sub"],
    )
    await comment.insert()
    return {"message": "Comment added successfully"}

# Generate AI Answer
@router.post("/questions/{question_id}/generate-answer")
async def generate_ai_answer_route(question_id: str, current_user: User = Depends(verify_in_company)):
    question = await Question.get(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Check if AI Answering is enabled for the company
    company = await User.find_one(User.id == current_user["sub"]).company
    if not company.ai_answer_enabled:
        raise HTTPException(status_code=403, detail="AI-generated answers are disabled")

    ai_answer = await generate_ai_answer(question.title, question.description)
    answer = Answer(
        question_id=question_id,
        answer=ai_answer,
        user_id=None,  # AI-generated answers have no user
        upvotes=0,
        is_ai=True,
    )
    await answer.insert()
    return {"message": "AI-generated answer added successfully", "answer": ai_answer}
