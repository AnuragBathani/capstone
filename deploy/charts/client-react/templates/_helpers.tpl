{{- define "client-react.labels" -}}
app: client-react-nginx
app.kubernetes.io/name: client-react-nginx
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
