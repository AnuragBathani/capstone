{{- define "api-node.labels" -}}
app: api-node
app.kubernetes.io/name: api-node
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
