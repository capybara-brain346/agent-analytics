{{- define "aa.name" -}}{{ .Release.Name }}{{- end -}}

{{- define "aa.labels" -}}
app.kubernetes.io/part-of: agent-analytics
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Environment for api, worker and migrate. DATABASE_URL comes from the CloudNativePG app secret. */}}
{{- define "aa.apiEnv" -}}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "aa.name" . }}-pg-app
      key: uri
- name: S3_ENDPOINT_URL
  value: {{ .Values.inbox.endpointURL | quote }}
- name: S3_BUCKET
  value: {{ .Values.inbox.bucket | quote }}
- name: S3_REGION
  value: {{ .Values.inbox.region | quote }}
- name: OFFLINE
  value: {{ .Values.offline | quote }}
- name: LOG_LEVEL
  value: {{ .Values.logLevel | quote }}
{{- with .Values.llm.model }}
- name: LLM_MODEL
  value: {{ . | quote }}
{{- end }}
- name: LLM_BASE_URL
  value: {{ .Values.llm.baseURL | quote }}
{{- end -}}
