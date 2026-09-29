"""Experimental QLoRA training starter for image-grounding ChatML datasets.

Expected dataset: JSONL records with a ``messages`` field, matching the output
of ``src.dataset.loader.to_chatml``. VLM data collators and target modules vary
by model family; verify the model card and smoke-test on a tiny split first.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="ChatML JSONL training data")
    parser.add_argument("--model", default="HuggingFaceTB/SmolVLM-500M-Instruct")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/visioncraft-qlora"))
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--load-in-4bit", action="store_true", help="Requires compatible CUDA and bitsandbytes")
    args = parser.parse_args()
    if not args.dataset.is_file():
        parser.error(f"Dataset not found: {args.dataset}")
    if args.steps <= 0:
        parser.error("--steps must be positive")

    try:
        import torch
        from datasets import load_dataset
        from peft import LoraConfig, prepare_model_for_kbit_training
        from transformers import AutoModelForVision2Seq, AutoProcessor, BitsAndBytesConfig, TrainingArguments
        from trl import SFTTrainer
    except ImportError as exc:
        raise SystemExit(f"Training dependencies are missing. Install requirements.txt. Details: {exc}") from exc

    if args.load_in_4bit and not torch.cuda.is_available():
        raise SystemExit("4-bit QLoRA requires a CUDA GPU; omit --load-in-4bit for a supported non-quantized setup.")
    quantization_config = BitsAndBytesConfig(load_in_4bit=True) if args.load_in_4bit else None
    model = AutoModelForVision2Seq.from_pretrained(
        args.model,
        device_map="auto",
        torch_dtype="auto",
        quantization_config=quantization_config,
    )
    if args.load_in_4bit:
        model = prepare_model_for_kbit_training(model)
    processor = AutoProcessor.from_pretrained(args.model)
    dataset = load_dataset("json", data_files=str(args.dataset), split="train")
    if "messages" not in dataset.column_names:
        raise SystemExit("Dataset must contain a 'messages' column; see src/dataset/loader.py.")
    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )
    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        max_steps=args.steps,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        gradient_checkpointing=True,
        logging_steps=5,
        save_steps=max(1, args.steps // 2),
        report_to="none",
        remove_unused_columns=False,
        fp16=torch.cuda.is_available(),
    )
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        processing_class=processor,
        peft_config=lora_config,
    )
    trainer.train()
    trainer.save_model(str(args.output_dir))
    processor.save_pretrained(str(args.output_dir))
    print(f"Adapter and processor saved to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
