import os

import numpy as np
from create_base_filename import create_base_filename
from gen_tortoise import generate_tortoise_n
from get_date import get_date
from get_speaker_gender import get_speaker_gender
from models.bark.bark import SAMPLE_RATE, generate_audio
from scipy.io.wavfile import write as write_wav
import json
from models.bark.bark.generation import SUPPORTED_LANGS
import gradio as gr
from models.tortoise.tortoise.utils.audio import get_voices
from save_waveform_plot import save_waveform_plot
from model_manager import model_manager
from config import config

value_empty_history = "Empty history"
value_use_last_gen = "or Use last generation as history"
value_use_voice = "or Use a voice:"
history_settings = [value_empty_history, value_use_last_gen, value_use_voice]

value_short_prompt = "Short prompt (<15s)"
value_split_lines = "Split prompt by lines"
value_split_length = "Split prompt by length"
long_prompt_choices = [value_short_prompt,
                       value_split_lines,
                       #   value_split_length
                       ]

value_reuse_history = "Reuse history"
value_use_voice_history = "Use voice history"
value_empty_history = "Empty history (not recommended)"
long_prompt_history_choices = [
    value_reuse_history, value_use_voice_history, value_empty_history
]

last_generation = None


def create_voice_string(language, speaker_id, useV2):
    history_prompt = f"{SUPPORTED_LANGS[language][1]}_speaker_{speaker_id}"
    if useV2:
        history_prompt = os.path.join("v2", history_prompt)
    return history_prompt


def generate_choice_string(useV2, language, speaker_id):
    history_prompt = create_voice_string(language, speaker_id, useV2)
    gender = get_speaker_gender(history_prompt)
    return gr.Markdown.update(
        value=f"Chosen voice: {history_prompt}, Gender: {gender}"
    )


def get_history_prompt_verbal(history_prompt, use_last_generation):
    return "last_generation" if use_last_generation else (history_prompt or "None")


def generate(prompt, history_setting, language=None, speaker_id=0, useV2=False, text_temp=0.7, waveform_temp=0.7, history_prompt=None):
    if not model_manager.models_loaded:
        model_manager.reload_models(config)

    use_voice = history_setting == value_use_voice
    use_last_generation = history_setting == value_use_last_gen

    global last_generation
    if history_prompt is None:
        if use_last_generation and last_generation is not None:
            history_prompt = last_generation
        else:
            history_prompt = create_voice_string(
                language, speaker_id, useV2) if use_voice else None
        history_prompt_verbal = get_history_prompt_verbal(
            history_prompt, use_last_generation)
    else:
        history_prompt_verbal = history_prompt if isinstance(
            history_prompt, str) else "continued_generation"

    print("Generating: '''", prompt, "'''")
    print("Parameters: history_prompt:", history_prompt_verbal,
          "text_temp:", text_temp, "waveform_temp:", waveform_temp,
          "useV2:", useV2, "use_voice:", use_voice, "use_last_generation", use_last_generation)
    full_generation, audio_array = generate_audio(
        prompt, history_prompt=history_prompt, text_temp=text_temp, waveform_temp=waveform_temp, output_full=True)

    last_generation = full_generation

    model = "bark"
    date = get_date()
    base_filename = create_base_filename(
        history_prompt_verbal, "outputs", model, date)
    filename = f"{base_filename}.wav"
    write_wav(filename, SAMPLE_RATE, audio_array)
    filename_png = f"{base_filename}.png"
    save_waveform_plot(audio_array, filename_png)

    filename_json = f"{base_filename}.json"
    # Generate metadata for the audio file
    metadata = {
        "prompt": prompt,
        "language": SUPPORTED_LANGS[language][0] if use_voice else None,
        "speaker_id": speaker_id if use_voice else None,
        "history_prompt": history_prompt_verbal,
        "text_temp": text_temp,
        "waveform_temp": waveform_temp,
        "date": date,
        "filename": filename,
        "filename_png": filename_png,
        "filename_json": filename_json,
    }
    with open(filename_json, "w") as outfile:
        json.dump(metadata, outfile, indent=2)

    return [filename, filename_png, audio_array, full_generation]


def generate_multi(count=1):
    def gen(prompt, history_setting, language=None, speaker_id=0, useV2=False, text_temp=0.7, waveform_temp=0.7, long_prompt_radio=value_short_prompt, long_prompt_history_radio=value_reuse_history):
        if long_prompt_radio == value_short_prompt:
            filenames = []
            for i in range(count):
                filename, filename_png, _, _ = generate(
                    prompt, history_setting, language, speaker_id, useV2, text_temp=text_temp, waveform_temp=waveform_temp)
                filenames.extend((filename, filename_png))
            return filenames

        prompts = split_by_lines(prompt) if long_prompt_radio == value_split_lines else [
            prompt[i:i+200] for i in range(0, len(prompt), 200)]
        filenames = []

        # save last_generation
        global last_generation
        last_generation_copy = last_generation

        for i in range(count):
            pieces = []
            last_piece_history = None
            for prompt_piece in prompts:
                if long_prompt_history_radio == value_reuse_history:
                    history_prompt = last_piece_history
                elif long_prompt_history_radio == value_use_voice_history:
                    history_prompt = create_voice_string(
                        language, speaker_id, useV2)
                elif long_prompt_history_radio == value_empty_history:
                    history_prompt = None
                
                filename, filename_png, audio_array, last_piece_history = generate(
                    prompt_piece, history_setting, language, speaker_id, useV2, text_temp=text_temp, waveform_temp=waveform_temp, history_prompt=history_prompt)
                pieces += [audio_array]
            # restore last_generation
            last_generation = last_generation_copy
            
            filename = filename.replace(".wav", "_long.wav")
            audio_array_full = np.concatenate(pieces)
            write_wav(filename, SAMPLE_RATE, audio_array_full)
            filename_png = filename.replace(".wav", ".png")
            save_waveform_plot(audio_array_full, filename_png)

            filename_json = filename.replace(".wav", ".json")
            # Generate metadata for the audio file
            metadata = {
                "prompt": prompt,
                "language": SUPPORTED_LANGS[language][0],
                "speaker_id": speaker_id,
                "history_prompt": history_setting,
                "text_temp": text_temp,
                "waveform_temp": waveform_temp,
                "date": get_date(),
                "filename": filename,
                "filename_png": filename_png,
                "filename_json": filename_json,
            }

            with open(filename_json, "w") as outfile:
                json.dump(metadata, outfile, indent=2)

            filenames.extend((filename, filename_png))
        return filenames

    def split_by_lines(prompt):
        prompts = prompt.split("\n")
        prompts = [p.strip() for p in prompts]
        prompts = [p for p in prompts if len(p) > 0]
        return prompts

    return gen


def generation_tab_bark():
    with gr.Tab("Generation (Bark)"):
        history_setting = gr.Radio(
            history_settings,
            value="Empty history",
            type="value",
            label="History Prompt (voice) setting:"
        )

        with gr.Row():
            useV2 = gr.Checkbox(
                label="Use V2", value=False, visible=False)
            choice_string = gr.Markdown(
                "Chosen voice: en_speaker_0, Gender: Unknown", visible=False)

        languages = [lang[0] for lang in SUPPORTED_LANGS]
        languageRadio = gr.Radio(languages, type="index", show_label=False,
                                 value="English", visible=False)

        speaker_ids = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]
        speakerIdRadio = gr.Radio(speaker_ids, type="value",
                                  label="Speaker ID", value="0", visible=False)

        # Show the language and speakerId radios only when useHistory is checked
        history_setting.change(
            fn=lambda choice: [
                gr.Radio.update(visible=(choice == value_use_voice)),
                gr.Radio.update(visible=(choice == value_use_voice)),
                gr.Checkbox.update(visible=(choice == value_use_voice)),
                gr.Markdown.update(visible=(choice == value_use_voice)),
            ],
            inputs=[history_setting],
            outputs=[languageRadio, speakerIdRadio, useV2, choice_string])

        with gr.Row():
            with gr.Column():
                long_prompt_radio = gr.Radio(
                    long_prompt_choices, type="value", label="Prompt type", value=value_short_prompt, show_label=False)
                long_prompt_history_radio = gr.Radio(
                    long_prompt_history_choices, type="value", label="For each subsequent generation:", value=value_reuse_history)
            with gr.Column():
                text_temp = gr.Slider(label="Text temperature",
                                      value=0.7, minimum=0.0, maximum=1.0, step=0.1)
                waveform_temp = gr.Slider(
                    label="Waveform temperature", value=0.7, minimum=0.0, maximum=1.0, step=0.1)

        prompt = gr.Textbox(label="Prompt", lines=3,
                            placeholder="Enter text here...")

        inputs = [
            prompt,
            history_setting,
            languageRadio,
            speakerIdRadio,
            useV2,
            text_temp,
            waveform_temp,
            long_prompt_radio,
            long_prompt_history_radio,
        ]

        voice_inputs = [
            useV2,
            languageRadio,
            speakerIdRadio
        ]

        for i in voice_inputs:
            i.change(
                fn=generate_choice_string,
                inputs=voice_inputs,
                outputs=[choice_string])

        with gr.Row():
            audio_1 = gr.Audio(type="filepath", label="Generated audio")
            audio_2 = gr.Audio(
                type="filepath", label="Generated audio", visible=False)
            audio_3 = gr.Audio(
                type="filepath", label="Generated audio", visible=False)

        with gr.Row():
            image_1 = gr.Image(label="Waveform")
            image_2 = gr.Image(label="Waveform", visible=False)
            image_3 = gr.Image(label="Waveform", visible=False)

        outputs = [audio_1, image_1]
        outputs2 = [audio_2, image_2]
        outputs3 = [audio_3, image_3]
        # examples = [
        #     ["The quick brown fox jumps over the lazy dog."],
        #     ["To be or not to be, that is the question."],
        #     ["In a hole in the ground there lived a hobbit."],
        #     ["This text uses a history prompt, resulting in a more predictable voice.",
        #         True, "English", "0"],
        # ]

        with gr.Row():
            generate3_button = gr.Button("Generate 3")
            generate2_button = gr.Button("Generate 2")
            generate1_button = gr.Button("Generate", variant="primary")

        prompt.submit(fn=generate_multi(1), inputs=inputs, outputs=outputs)
        generate1_button.click(fn=generate_multi(1), inputs=inputs,
                               outputs=outputs)
        generate2_button.click(fn=generate_multi(2), inputs=inputs,
                               outputs=outputs + outputs2)
        generate3_button.click(fn=generate_multi(3), inputs=inputs,
                               outputs=outputs + outputs2 + outputs3)

        def show(count): return [
            gr.Audio.update(visible=True),
            gr.Image.update(visible=True),
            gr.Audio.update(visible=count > 1),
            gr.Image.update(visible=count > 1),
            gr.Audio.update(visible=count > 2),
            gr.Image.update(visible=count > 2),
        ]

        generate1_button.click(fn=lambda: show(
            1), outputs=outputs + outputs2 + outputs3)
        generate2_button.click(fn=lambda: show(
            2), outputs=outputs + outputs2 + outputs3)
        generate3_button.click(fn=lambda: show(
            3), outputs=outputs + outputs2 + outputs3)


def test():
    text_prompt = """
        Hello, my name is Suno. And, uh — and I like pizza. [laughs] 
        But I also have other interests such as playing tic tac toe.
    """

    history_prompt = "en_speaker_0"
    generate(text_prompt, True, history_prompt)
    generate(text_prompt, False, history_prompt)


css_tortoise = """
.btn-sm {
    min-width: 3em !important;
    flex-grow: 0 !important;
}
"""


def generation_tab_tortoise():
    with gr.Tab("Generation (Tortoise)"):
        prompt = gr.Textbox(label="Prompt", lines=3,
                            placeholder="Enter text here...")

        with gr.Row():
            # with gr.Box():
            # gr.Markdown("### Voice")
            with gr.Row():
                voice = gr.Dropdown(
                    choices=["random"] + list(get_voices()),
                    value="random",
                    # show_label=False,
                    label="Voice"
                )
                # voice.style(container=False)
                # reload_voices = gr.Button("🔁", elem_classes="btn-sm")
                # reload_voices.style(size="sm")
                # def reload_voices_fn():
                #     choices =
                #     print(choices)
                #     return [
                #         gr.Dropdown.update(choices=choices),
                #     ]
                # reload_voices.click(fn=reload_voices_fn, outputs=[voice])
            preset = gr.Dropdown(label="Preset", choices=[
                'ultra_fast',
                'fast',
                'standard',
                'high_quality',
            ], value="ultra_fast")
        # Args:
        # seed (int): The desired seed. Value must be within the inclusive range
        #     `[-0x8000_0000_0000_0000, 0xffff_ffff_ffff_ffff]`. Otherwise, a RuntimeError
        #     is raised. Negative inputs are remapped to positive values with the formula
        #     `0xffff_ffff_ffff_ffff + seed`.
        seed = gr.Textbox(label="Seed", lines=1,
                          placeholder="Enter seed here...", value="None", visible=False)
        cvvp_amount = gr.Slider(label="CVVP Amount",
                                value=0.0, minimum=0.0, maximum=1.0, step=0.1)

        inputs = [
            prompt,
            voice,
            preset,
            seed,
            cvvp_amount
        ]

        with gr.Row():
            audio_1 = gr.Audio(type="filepath", label="Generated audio")
            audio_2 = gr.Audio(
                type="filepath", label="Generated audio", visible=False)
            audio_3 = gr.Audio(
                type="filepath", label="Generated audio", visible=False)

        with gr.Row():
            image_1 = gr.Image(label="Waveform")
            image_2 = gr.Image(label="Waveform", visible=False)
            image_3 = gr.Image(label="Waveform", visible=False)

        outputs = [audio_1, image_1]
        outputs2 = [audio_2, image_2]
        outputs3 = [audio_3, image_3]

        with gr.Row():
            generate3_button = gr.Button("Generate 3")
            generate2_button = gr.Button("Generate 2")
            generate1_button = gr.Button("Generate", variant="primary")

        prompt.submit(fn=generate_tortoise_n(1),
                      inputs=inputs, outputs=outputs)
        generate1_button.click(fn=generate_tortoise_n(1),
                               inputs=inputs, outputs=outputs)
        generate2_button.click(fn=generate_tortoise_n(2), inputs=inputs,
                               outputs=outputs + outputs2)
        generate3_button.click(fn=generate_tortoise_n(3), inputs=inputs,
                               outputs=outputs + outputs2 + outputs3)

        def show_closure(count):
            def show():
                return [
                    gr.Audio.update(visible=True),
                    gr.Image.update(visible=True),
                    gr.Audio.update(visible=count > 1),
                    gr.Image.update(visible=count > 1),
                    gr.Audio.update(visible=count > 2),
                    gr.Image.update(visible=count > 2),
                ]
            return show

        generate1_button.click(fn=show_closure(
            1), outputs=outputs + outputs2 + outputs3)
        generate2_button.click(fn=show_closure(
            2), outputs=outputs + outputs2 + outputs3)
        generate3_button.click(fn=show_closure(
            3), outputs=outputs + outputs2 + outputs3)