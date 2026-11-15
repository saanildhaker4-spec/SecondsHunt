# =====================================================================
#  VOICE HELPER (Windows PowerShell) - used by voice.py
# =====================================================================
#  Uses the speech tools that are built into Windows:
#    -Say      text to speak aloud
#    -Choices  the answers to listen for, separated by |
#    -Seconds  how long to wait for the caller to answer
#    -Wave     (testing only) listen to a .wav file, not the microphone
#
#  It prints one line:   HEARD|<what it heard>|<confidence 0 to 1>
#  or, if something went wrong:   ERROR|<message>
# =====================================================================
param(
    [string]$Say = "",
    [string]$Choices = "",
    [int]$Seconds = 7,
    [string]$Wave = ""
)

try {
    Add-Type -AssemblyName System.Speech

    # 1. speak the question
    if ($Say -ne "") {
        $voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
        $voice.Speak($Say)
        $voice.Dispose()
    }

    # 2. listen for one of the allowed answers
    if ($Choices -ne "") {
        $culture = New-Object System.Globalization.CultureInfo("en-US")
        $ear = New-Object System.Speech.Recognition.SpeechRecognitionEngine($culture)

        $allowed = New-Object System.Speech.Recognition.Choices
        $allowed.Add([string[]]($Choices -split "\|"))
        $builder = New-Object System.Speech.Recognition.GrammarBuilder
        $builder.Culture = $culture
        $builder.Append($allowed)
        $ear.LoadGrammar((New-Object System.Speech.Recognition.Grammar($builder)))

        if ($Wave -ne "") {
            $ear.SetInputToWaveFile($Wave)
        } else {
            $ear.SetInputToDefaultAudioDevice()
            [console]::beep(900, 150)      # beep = "speak now"
        }

        $result = $ear.Recognize([TimeSpan]::FromSeconds($Seconds))
        if ($result) {
            "HEARD|" + $result.Text + "|" + $result.Confidence
        } else {
            "HEARD||0"
        }
        $ear.Dispose()
    }
}
catch {
    "ERROR|" + $_.Exception.Message
}
