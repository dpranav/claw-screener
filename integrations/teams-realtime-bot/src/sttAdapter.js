class SttAdapter {
  // eslint-disable-next-line class-methods-use-this
  async transcribeFrame(_frame) {
    throw new Error("transcribeFrame not implemented");
  }
}

class PassthroughSttAdapter extends SttAdapter {
  async transcribeFrame(frame) {
    const text = String(frame.text || "").trim();
    return { text, confidence: 1.0, provider: "passthrough" };
  }
}

class AzureSpeechSttAdapter extends SttAdapter {
  constructor({
    enabled,
    azureSpeechKey,
    azureSpeechRegion,
    sttLanguage,
    sttSampleRateHz,
    sttBitsPerSample,
    sttChannels,
    sttMinConfidence,
  }) {
    super();
    this.enabled = enabled;
    this.azureSpeechKey = azureSpeechKey;
    this.azureSpeechRegion = azureSpeechRegion;
    this.sttLanguage = sttLanguage || "en-US";
    this.sttSampleRateHz = Number(sttSampleRateHz || 16000);
    this.sttBitsPerSample = Number(sttBitsPerSample || 16);
    this.sttChannels = Number(sttChannels || 1);
    this.sttMinConfidence = Number.isFinite(sttMinConfidence) ? sttMinConfidence : 0;
  }

  async transcribeFrame(frame) {
    const text = String(frame.text || "").trim();
    if (text) return { text, confidence: 1.0, provider: "azure_speech" };
    if (!this.enabled) {
      return { text: "", confidence: 0.0, provider: "azure_speech" };
    }

    const audioBase64 = String(frame.audioBase64 || "").trim();
    if (!audioBase64) {
      return { text: "", confidence: 0.0, provider: "azure_speech" };
    }

    let speechsdk;
    try {
      // Optional dependency until adapter is enabled in runtime.
      // eslint-disable-next-line global-require, import/no-extraneous-dependencies
      speechsdk = require("microsoft-cognitiveservices-speech-sdk");
    } catch (err) {
      throw new Error(
        "Azure Speech SDK missing. Run npm install in integrations/teams-realtime-bot."
      );
    }

    const audioBytes = Buffer.from(audioBase64, "base64");
    if (!audioBytes.length) {
      return { text: "", confidence: 0.0, provider: "azure_speech" };
    }

    const speechConfig = speechsdk.SpeechConfig.fromSubscription(
      this.azureSpeechKey,
      this.azureSpeechRegion
    );
    speechConfig.speechRecognitionLanguage = this.sttLanguage;
    speechConfig.setProperty(
      speechsdk.PropertyId.SpeechServiceResponse_RequestWordLevelTimestamps,
      "true"
    );
    const format = speechsdk.AudioStreamFormat.getWaveFormatPCM(
      this.sttSampleRateHz,
      this.sttBitsPerSample,
      this.sttChannels
    );
    const pushStream = speechsdk.AudioInputStream.createPushStream(format);
    pushStream.write(audioBytes);
    pushStream.close();

    const audioConfig = speechsdk.AudioConfig.fromStreamInput(pushStream);
    const recognizer = new speechsdk.SpeechRecognizer(speechConfig, audioConfig);

    const result = await new Promise((resolve, reject) => {
      recognizer.recognizeOnceAsync(resolve, reject);
    }).finally(() => {
      recognizer.close();
    });

    if (!result || result.reason !== speechsdk.ResultReason.RecognizedSpeech) {
      return { text: "", confidence: 0.0, provider: "azure_speech" };
    }

    const recognizedText = String(result.text || "").trim();
    const confidence = extractConfidence(result, speechsdk);
    if (!recognizedText || confidence < this.sttMinConfidence) {
      return { text: "", confidence, provider: "azure_speech" };
    }

    return { text: recognizedText, confidence, provider: "azure_speech" };
  }
}

function extractConfidence(result, speechsdk) {
  try {
    const raw =
      typeof result.properties.getProperty === "function"
        ? result.properties.getProperty(
            speechsdk.PropertyId.SpeechServiceResponse_JsonResult
          )
        : "";
    if (!raw) return 0;
    const parsed = JSON.parse(raw);
    const nbest = Array.isArray(parsed?.NBest) ? parsed.NBest : [];
    if (!nbest.length) return 0;
    const conf = Number(nbest[0]?.Confidence ?? 0);
    return Number.isFinite(conf) ? conf : 0;
  } catch {
    return 0;
  }
}

function createSttAdapter(config) {
  const mode = String(config.sttAdapter || "passthrough").toLowerCase();
  if (mode === "azure_speech") {
    return new AzureSpeechSttAdapter({
      enabled: Boolean(config.azureSpeechKey && config.azureSpeechRegion),
      azureSpeechKey: config.azureSpeechKey,
      azureSpeechRegion: config.azureSpeechRegion,
      sttLanguage: config.sttLanguage,
      sttSampleRateHz: config.sttSampleRateHz,
      sttBitsPerSample: config.sttBitsPerSample,
      sttChannels: config.sttChannels,
      sttMinConfidence: config.sttMinConfidence,
    });
  }
  return new PassthroughSttAdapter();
}

module.exports = {
  createSttAdapter,
  SttAdapter,
};

