听力：
1、取题：根据paper_id、section_mapping、section取question.enabled_prac=1的题目，单题录音在question.audio_url，共享音频用question.group_id查question_shared_audio
2、存储：practice_answer题目快照存question.section_title、question.content、question.passage、question.audioUrl、question_shared_audio.shareAudioUrl，选项快照存question.option_content
3、出结果：交卷即出结果。逐题比对 answer 和 question.answer算出总题数、已答题数、答对数、答错数、正确率，写回记录。未作答的一律记为错，所以「错题数 = 总题数 − 答对数」。practice_record.current_question_number是practice_record.question_ids的数组下标+1、practice_record.idempotency_key的拼接方式是module-recordid-submit-1


阅读：
1、取题：根据paper_id、section_mapping、section取question.enabled_prac=1的题目，单题的题目、选项在question上，共享材料在question_group上
2、存储：practice_answer题目快照存question.section_title、question.content、question.passage、question_group.content、question_group.passage，选项快照存question.option_content、question_group.option_content
3、出结果：交卷即出结果。逐题比对 answer 和 question.answer算出总题数、已答题数、答对数、答错数、正确率，写回记录。未作答的一律记为错，所以「错题数 = 总题数 − 答对数」。practice_record.current_question_number是practice_record.question_ids的数组下标+1、practice_record.idempotency_key的拼接方式是module-recordid-submit-1

写作：
1、取题：根据paper_id、section_mapping、section取question.enabled_prac=1的题目
2、存储：
3、出结果：

翻译：
1、取题：根据paper_id、section_mapping、section取question.enabled_prac=1的题目
2、存储：
3、出结果：

口语：
1、取题：根据paper_id、section_mapping、section取question.enabled_prac=1的题目或speaking_exam_paper_question.enabled_prac=1（speaking_exam_paper_question默认section_mapping等于SEC_SPEAKING）
2、存储：
3、出结果：