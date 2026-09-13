{{- define "api-golang.name" -}}api-golang{{- end -}}

{{- define "api-golang.labels" -}}
app: api-golang
app.kubernetes.io/name: api-golang
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "api-golang.databaseUrl" -}}
postgres://{{ .Values.database.user }}:{{ .Values.database.password }}@{{ .Values.database.host }}:{{ .Values.database.port }}/{{ .Values.database.name }}
{{- end -}}
