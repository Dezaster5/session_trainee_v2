import { render, screen } from "@testing-library/react";

import { AnswerExplanation, QuestionImage } from "./QuestionMedia";

describe("QuestionImage", () => {
  it("renders visual question images", () => {
    render(<QuestionImage src="http://testserver/api/question-images/EIE-Q0044.png" />);

    const image = screen.getByRole("img", { name: "Иллюстрация к вопросу" });
    expect(image).toHaveAttribute("src", "http://testserver/api/question-images/EIE-Q0044.png");
  });

  it("does not render when there is no image", () => {
    const { container } = render(<QuestionImage src={null} />);

    expect(container).toBeEmptyDOMElement();
  });
});

describe("AnswerExplanation", () => {
  it("renders explanations after an answer is available", () => {
    render(<AnswerExplanation explanation="The correct option follows the definition." />);

    expect(screen.getByText("Пояснение")).toBeInTheDocument();
    expect(screen.getByText("The correct option follows the definition.")).toBeInTheDocument();
  });

  it("renders the formula block only when formula exists", () => {
    const { rerender } = render(<AnswerExplanation explanation="Review text" formula="" />);

    expect(screen.queryByText("Формула")).not.toBeInTheDocument();

    rerender(<AnswerExplanation explanation="Review text" formula="TR = P x Q" />);

    expect(screen.getByText("Формула")).toBeInTheDocument();
    expect(screen.getByText("TR = P x Q")).toBeInTheDocument();
  });
});
