#!/bin/bash
# ============================================================
# Converte cookies.txt para base64 e exibe para configurar
# no Render como variável de ambiente YOUTUBE_COOKIES_B64
# 
# Uso:
#   1. Exporte os cookies do YouTube via extensão "Get cookies.txt LOCALLY"
#      (Chrome/Firefox) enquanto estiver logado no YouTube
#   2. Salve como cookies.txt na pasta do projeto
#   3. Execute este script:  bash export_cookies.sh
#   4. Copie o valor e cole no Render > Environment > YOUTUBE_COOKIES_B64
# ============================================================
if [ ! -f cookies.txt ]; then
  echo "ERRO: cookies.txt não encontrado na pasta atual"
  exit 1
fi
echo ""
echo "Cole este valor no Render como YOUTUBE_COOKIES_B64:"
echo "----------------------------------------------------"
base64 -w 0 cookies.txt
echo ""
echo "----------------------------------------------------"
echo "Depois, delete o cookies.txt local por segurança."
