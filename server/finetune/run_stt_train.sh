#!/bin/zsh
# STT 추가 학습 한 번 돌리기(2026-11-17): 기준 재기 → 학습 세트 → LoRA 학습 → 합치기 → 학습 뒤 재기.
# 사용: run_stt_train.sh <학습 소리 폴더> [반복 수, 기본 2]
#   학습 소리 폴더: <문장 번호>.wav 또는 <번호>_<이름>.wav (번호 = finetune/train_sentences.txt 순서, 1부터)
#   (11/18: 기계 목소리 학습은 실패해서 맥 Qwen3-TTS 로 소리 만들기(tts)는 지웠다. 실제 사람 녹음만 쓴다.)
# 사용자가 '시작해'라고 할 때만 건다. IntelliJ·Claude 를 꺼도 돌게 부모 없이 띄울 것(caffeinate -i -s).
set -u
SERVER=/Users/teddy/Desktop/UPTIVE/STT-TTS/server
W=$SERVER/.train/stt-ko
ASR_PY=$SERVER/.venv-asr/bin/python
SWIFT=$W/venv/bin/swift
BASE=$SERVER/.models/qwen3_asr_1.7b_ko
AUDIO=${1:?학습 소리 폴더를 주세요}
EPOCHS=${2:-2}
STAMP=$(date +%Y%m%d-%H%M)
OUT=$W/runs/$STAMP
mkdir -p $W/logs $OUT
LOG=$W/logs/run-$STAMP.log
exec >> $LOG 2>&1
status() { echo "$1" > $W/logs/status.txt; echo "--- $1 $(date '+%T')"; }
fail() { status "FAILED: $1 ($STAMP)"; exit 1; }
echo "=== start $STAMP audio=$AUDIO epochs=$EPOCHS"
cd $SERVER

status "1/5 eval-base"
[ -f $W/eval/base.json ] || $ASR_PY -m finetune.build_dataset eval || fail eval-set
[ -f $W/eval/base.json ] || $ASR_PY -m finetune.evaluate --model $BASE --name base || fail eval-base

status "2/5 train-set"
$ASR_PY -m finetune.build_dataset train --audio-dir $AUDIO || fail train-set

status "3/5 train"
PYTORCH_ENABLE_MPS_FALLBACK=1 $SWIFT sft --model $BASE --model_type qwen3_asr --tuner_type lora \
  --dataset $W/data/train.jsonl --torch_dtype bfloat16 --num_train_epochs $EPOCHS \
  --per_device_train_batch_size 1 --gradient_accumulation_steps 8 --learning_rate 1e-4 \
  --lora_rank 16 --lora_alpha 32 --target_modules all-linear --freeze_vit true \
  --save_strategy epoch --save_total_limit 3 --logging_steps 5 --split_dataset_ratio 0 \
  --dataloader_num_workers 0 --report_to none --output_dir $OUT/train || fail train

status "4/5 merge"
CK=$(ls -d $OUT/train/v*/checkpoint-* | sort -t- -k2 -n | tail -1)
$SWIFT export --adapters $CK --merge_lora true --output_dir $OUT/merged || fail merge

status "5/5 eval-lora"
$ASR_PY -m finetune.evaluate --model $OUT/merged --name lora-$STAMP || fail eval-lora
status "DONE $STAMP"
echo "=== done $(date '+%F %T')"
