param([string]$Saida)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile($Saida, $fmt)
$linhas = @(
 @("Microsoft Maria Desktop","Bom dia, doutor. Eu gostaria de entender em que pé está o processo de execução que o banco moveu contra a minha empresa no ano passado."),
 @("Microsoft Daniel","Bom dia, dona Helena. Vou resumir a situação. O processo está na fase de penhora, e o juiz determinou o bloqueio de valores nas contas da sociedade na semana passada."),
 @("Microsoft Maria Desktop","Esse bloqueio atinge também a conta pessoal dos sócios? Eu preciso pagar a folha de pagamento até o dia cinco, e são cento e vinte funcionários."),
 @("Microsoft Daniel","A decisão atinge apenas as contas da pessoa jurídica. Mesmo assim, vamos protocolar hoje uma petição pedindo o desbloqueio parcial, com base na natureza alimentar dos salários."),
 @("Microsoft Maria Desktop","Entendi. E qual é a chance de o juiz aceitar esse pedido? Já tivemos uma decisão desfavorável em dois mil e vinte e dois, naquele outro caso."),
 @("Microsoft Daniel","Nesse caso anterior a fundamentação era diferente. Aqui existe um precedente recente do Superior Tribunal de Justiça, que reconhece a impenhorabilidade de verbas destinadas ao pagamento de salários."),
 @("Microsoft Maria Desktop","Ótimo. Outra dúvida: a dívida original era de oitocentos mil reais, e hoje o banco cobra mais de um milhão e trezentos mil. Esse valor está correto?"),
 @("Microsoft Daniel","Precisamos revisar o cálculo. Os juros contratuais, a correção monetária e a multa foram aplicados em cima do saldo total, e isso pode configurar capitalização indevida de juros."),
 @("Microsoft Maria Desktop","O senhor acha que vale a pena pedir uma perícia contábil? Eu soube que o custo de um perito pode passar de quinze mil reais."),
 @("Microsoft Daniel","Vale, sim. Se o perito confirmar o excesso de cobrança, o valor da execução cai de forma significativa, e o custo da perícia é muito menor que a diferença."),
 @("Microsoft Maria Desktop","Perfeito. Então vamos pedir a perícia e o desbloqueio parcial. Existe algum prazo que eu não possa perder nos próximos dias?"),
 @("Microsoft Daniel","Sim. O prazo para os embargos termina no dia doze de dezembro. Vou preparar a minuta e enviar para a sua revisão até a próxima quarta-feira, às dez horas da manhã."),
 @("Microsoft Maria Desktop","Combinado. Mais uma coisa, doutor: a minha contadora, a Fernanda, vai precisar de acesso aos documentos do processo para montar o demonstrativo de débito."),
 @("Microsoft Daniel","Sem problema. Vou liberar uma pasta compartilhada com as cópias digitalizadas dos autos, e a Fernanda poderá consultar tudo com o código de acesso que eu enviar por e-mail."),
 @("Microsoft Maria Desktop","Muito obrigada. Se o juiz marcar audiência de conciliação, eu preciso comparecer pessoalmente ou o senhor pode me representar?"),
 @("Microsoft Daniel","Pode ser por videoconferência, mas a presença da parte é recomendável, porque o banco costuma apresentar propostas de acordo com desconto na própria audiência."),
 @("Microsoft Maria Desktop","Entendo. Nesse caso, qual seria um bom acordo? Eu consigo pagar uma entrada de duzentos mil reais e parcelar o restante em sessenta meses."),
 @("Microsoft Daniel","Depende do resultado da perícia. Com o valor corrigido, uma entrada de vinte por cento e o saldo em sessenta parcelas pode ser uma proposta bastante razoável."),
 @("Microsoft Maria Desktop","Ótimo, doutor. Então ficamos assim: o senhor protocola a petição hoje, me envia a minuta dos embargos na quarta-feira e eu aguardo o contato do perito."),
 @("Microsoft Daniel","Exatamente. Qualquer novidade, eu aviso imediatamente pelo telefone. Tenha um bom dia, dona Helena, e fique tranquila, estamos acompanhando o caso de perto."),
 @("Microsoft Maria Desktop","Obrigada, doutor. Até logo.")
)
$pb = New-Object System.Speech.Synthesis.PromptBuilder
for ($r = 0; $r -lt 3; $r++) {
  foreach ($l in $linhas) {
    $pb.StartVoice($l[0]); $pb.AppendText($l[1]); $pb.EndVoice(); $pb.AppendBreak([TimeSpan]::FromMilliseconds(600))
  }
}
$s.Speak($pb)
$s.Dispose()
