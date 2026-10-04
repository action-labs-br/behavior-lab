// Labels stay separate from stable action IDs and model/dataset identifiers.
const PT_BR = {
  'Fold':'Dobre', '/ Learn':'/ Aprenda', 'Fold / Learn':'Dobre / Aprenda',
  'Language':'Idioma', 'Participate':'Participar', 'Presenter':'Apresentador', 'Leave session':'Sair da sessão',
  'A small experiment in learning from people':'Um pequeno experimento de aprendizado com pessoas',
  'Your folds teach the model.':'Suas dobraduras ensinam o modelo.',
  'Take a photo':'Tire uma foto', 'before':'antes',
  'each action. We pair the image with what you do next.':'de cada ação. Associamos a imagem ao que você fará em seguida.',
  'Photos are used for this demonstration and retained until the presenter manually deletes them. Hands and backgrounds may appear; keep faces and sensitive information out of frame. The presenter can view your photos and display name.':'As fotos são usadas nesta demonstração e ficam armazenadas até que o apresentador as exclua manualmente. Mãos e objetos ao fundo podem aparecer; evite incluir rostos e informações sensíveis. O apresentador pode ver suas fotos e seu nome de exibição.',
  'Display name':'Nome de exibição', 'Event code':'Código do evento', 'Join experiment':'Participar do experimento',
  'Start or resume a run':'Iniciar ou retomar uma tentativa',
  'Take a photo of the paper':'Tire uma foto do papel',
  'Photo of the blank paper':'Foto do papel em branco',
  'Now photograph the paper after this fold. This will be the starting state for the next fold.':'Agora fotografe o papel depois desta dobra. Esta será a posição inicial da próxima dobra.',
  'Paper after this fold':'Papel depois desta dobra',
  'Upload folded state':'Enviar foto após a dobra',
  'Move to the next fold':'Avançar para a próxima dobra',
  'I performed this fold':'Fiz esta dobra',
  'Photo of the current state':'Foto do estado atual',
  'Next fold: {action}':'Próxima dobra: {action}',
  'Diagram for {action}':'Ilustração: {action}',
  'Continue to folding instructions':'Continuar para as instruções da dobra',
  'Back to current-state photo':'Voltar à foto do estado atual',
  'as it looks now, before folding':'como ele está agora, antes de dobrar',
  '. Include the whole sheet and leave a little space around it.':'. Inclua a folha inteira e deixe um pouco de espaço ao redor.',
  'Current paper state':'Estado atual do papel', 'Your selected paper photo':'Foto do papel selecionada',
  'Confirm and upload photo':'Confirmar e enviar foto',
  'Photo confirmed. Now perform this action:':'Foto confirmada. Agora execute esta ação:',
  'I performed the fold — next step':'Fiz a dobra — próxima etapa',
  'Airplane complete.':'Avião pronto.',
  'Your photos are now demonstrations for the model. Thanks for contributing!':'Suas fotos agora são demonstrações para o modelo. Obrigado por contribuir!',
  'Make another airplane':'Fazer outro avião', 'Presenter access':'Acesso do apresentador',
  'Password':'Senha', 'Sign in':'Entrar', 'Dataset':'Conjunto de dados', 'Train':'Treinar', 'Live demo':'Demonstração ao vivo',
  'Experiment dashboard':'Painel do experimento', 'Refresh dataset':'Atualizar conjunto de dados',
  'Learn from demonstrations':'Aprender com demonstrações',
  'Hold out a whole participant to measure generalization. Every action needs at least two training photos after the split.':'Reserve todas as fotos de um participante para avaliar a generalização. Cada ação precisa de pelo menos duas fotos de treinamento após essa separação.',
  'Evaluation participant':'Participante reservado para avaliação',
  'Automatic participant holdout':'Selecionar automaticamente um participante para avaliação',
  'Training only — no held-out evaluation':'Somente treinamento — sem avaliação com participante reservado',
  'Train model':'Treinar modelo', 'Model history':'Histórico de modelos',
  'Rehearse with real photos, train a model, then mark the verified version as your fallback. Activating it is always manual.':'Ensaie com fotos reais, treine um modelo e marque a versão verificada como modelo de reserva. A ativação é sempre manual.',
  'What would you do next?':'O que você faria em seguida?',
  'Show the model an unfinished airplane. It only knows the configured actions; it cannot detect that you are finished.':'Mostre ao modelo um avião inacabado. Ele conhece apenas as ações configuradas e não consegue detectar que você terminou.',
  'New paper state':'Novo estado do papel', 'Predict next action':'Prever próxima ação',
  'These are model probabilities, not guarantees of correctness. Try a new background or an unfamiliar fold.':'Estas são probabilidades do modelo, não garantias de acerto. Experimente outro fundo ou uma dobra diferente.',
  'Demonstration gallery':'Galeria de demonstrações', 'Filter by action':'Filtrar por ação', 'All actions':'Todas as ações',
  'After the presentation':'Após a apresentação',
  'Delete participant records, runs and photos manually. Trained models are retained for reuse. Collection closes during cleanup.':'Exclua manualmente os registros dos participantes, as tentativas e as fotos. Os modelos treinados são mantidos para reutilização. A coleta é encerrada durante a limpeza.',
  'Type':'Digite', 'to delete this dataset':'para excluir este conjunto de dados',
  'Delete dataset and close collection':'Excluir conjunto de dados e encerrar coleta', 'Reopen collection':'Reabrir coleta',
  'Previously issued uploads expire after five minutes. Repeat cleanup after that interval to remove any late uploads.':'As autorizações de envio já emitidas expiram após cinco minutos. Repita a limpeza após esse intervalo para remover fotos enviadas com atraso.',
  'Observe → demonstrate → learn → test':'Observar → demonstrar → aprender → testar',
  'welcome':'Olá, {name}. Vamos fazer uma demonstração?', 'step':'Etapa {current} de {total}',
  'Choose a photo first':'Selecione uma foto primeiro', 'Choose an image smaller than 10 MiB':'Selecione uma imagem menor que 10 MiB',
  'Upload failed. Your step is saved; try again.':'Falha no envio. Sua etapa foi salva; tente novamente.',
  'Participant':'Participante', 'Participants':'Participantes', 'Completed runs':'Tentativas concluídas',
  'Eligible photos':'Fotos disponíveis para treinamento', 'Excluded':'Excluídas do treinamento',
  'Include sample':'Incluir amostra', 'Exclude sample':'Excluir amostra',
  'gallery':'{name} · Tentativa {run} · Etapa {step} · {action}', 'photoBefore':'Papel antes de: {action}',
  'Collection closed.':'Coleta encerrada.', 'No active model.':'Nenhum modelo ativo.',
  'No fallback prepared yet.':'Nenhum modelo de reserva preparado.', 'activeModel':'Modelo ativo ({source}): {id}',
  'fallbackSaved':'Modelo de reserva salvo: {id}', 'live':'treinado ao vivo', 'fallback':'de reserva',
  'not evaluated':'não avaliada', 'Mark as fallback':'Marcar como modelo de reserva', 'Activate':'Ativar',
  'modelHistory':'{date} · {id} · {train} fotos de treinamento / {test} de teste · acurácia de teste: {accuracy}',
  'IDLE':'Aguardando', 'QUEUED':'Na fila', 'RUNNING':'Treinando', 'READY':'Pronto', 'FAILED':'Falhou',
  'embeddingProgress':' — extração de características {done}/{total}',
  'metrics':'Acurácia de treinamento: {train} · Acurácia com participante reservado: {test} · {mode}',
  'participant_holdout':'avaliação com participante reservado', 'training_only_no_holdout':'somente treinamento, sem participante reservado',
  'confusion':'Matriz de confusão: linhas = classe real, colunas = classe prevista. Ordem das classes: {classes}',
  'predictionModel':'Modelo {source}: {id}',
  'Incorrect event code':'Código do evento incorreto', 'Enter a display name':'Digite um nome de exibição',
  'Incorrect password':'Senha incorreta', 'Presenter login required':'Entre como apresentador',
  'Join the experiment first':'Participe do experimento primeiro', 'Collection is closed':'A coleta está encerrada',
  'Run not found':'Tentativa não encontrada', 'Instructions changed; start a new run':'As instruções mudaram; inicie uma nova tentativa',
  'Sample not found':'Amostra não encontrada', 'Upload must match the current step':'A foto deve corresponder à etapa atual',
  'Upload the current paper state before performing this fold':'Envie a foto do estado atual do papel antes de fazer esta dobra',
  'Upload the folded paper state before moving to the next fold':'Envie a foto do papel dobrado antes de avançar para a próxima dobra',
  'There is no paper state to upload at this step':'Não há um estado do papel para enviar nesta etapa',
  'Choose JPEG or PNG; convert HEIC before uploading':'Selecione JPEG ou PNG; converta arquivos HEIC antes de enviá-los',
  'Image exceeds 10 MiB; choose a smaller image':'A imagem excede 10 MiB; selecione uma imagem menor',
  'Photo already confirmed':'Foto já confirmada',
  'Upload missing or invalid; please retry with a JPEG/PNG under 10 MiB':'Foto ausente ou inválida; tente novamente com um arquivo JPEG/PNG menor que 10 MiB',
  'Confirm the photo before performing and completing the fold':'Confirme a foto antes de fazer e concluir a dobra',
  'Another operation is in progress; try again shortly':'Há outra operação em andamento; tente novamente em breve',
  'Held-out participant has no eligible samples':'O participante reservado para avaliação não tem amostras disponíveis',
  'Training lease expired; start training again':'O tempo limite do treinamento expirou; inicie o treinamento novamente',
  'Training lease expired before activation':'O tempo limite do treinamento expirou antes da ativação',
  'Training interrupted or exceeded 15 minutes; retry. Previous model retained.':'O treinamento foi interrompido ou ultrapassou 15 minutos; tente novamente. O modelo anterior foi mantido.',
  'Model missing or incompatible with this experiment':'Modelo ausente ou incompatível com este experimento',
  'Train or activate a model first':'Treine ou ative um modelo primeiro',
  'Active model is incompatible; train again':'O modelo ativo é incompatível; treine novamente',
  'Type the experiment ID to confirm deletion':'Digite o identificador do experimento para confirmar a exclusão',
  'Collection closed and dataset deleted. Models retained. Repeat after 5 minutes to remove any late uploads.':'Coleta encerrada e conjunto de dados excluído. Os modelos foram mantidos. Repita após 5 minutos para remover fotos enviadas com atraso.',
  'Use a JPEG or PNG image':'Use uma imagem JPEG ou PNG', 'Image exceeds 25 megapixels':'A imagem excede 25 megapixels',
  'Cannot decode image; please recapture as JPEG or PNG':'Não foi possível ler a imagem; tire outra foto em JPEG ou PNG',
};
const EN = {
  welcome:'Welcome, {name}. Ready to make a demonstration?', step:'Step {current} of {total}',
  gallery:'{name} · Run {run} · Step {step} · {action}', photoBefore:'Paper before {action}',
  activeModel:'Active {source} model: {id}', fallbackSaved:'Fallback saved: {id}',
  modelHistory:'{date} · {id} · {train} training / {test} test photos · test accuracy {accuracy}',
  embeddingProgress:' — embeddings {done}/{total}',
  metrics:'Training accuracy {train} · Held-out accuracy {test} · {mode}',
  confusion:'Confusion matrix: rows = actual, columns = predicted. Class order: {classes}',
  predictionModel:'{source} model {id}',
};
const PAPER_PT = {
  name:'Aprenda a dobrar um avião de papel',
  introduction:'Use papel retangular tamanho Carta. Fotografe a folha inteira sobre uma superfície de cor contrastante antes de cada ação. Mantenha o nariz do avião apontado para longe de você. Reserve de 5 a 10 minutos.',
  steps:{
    crease_center:['Faça a dobra central','Dobre a folha ao meio no sentido do comprimento, alinhe as bordas longas, marque a dobra e desdobre. Mantenha a marca da dobra na vertical.'],
    fold_left_corner:['Dobre o canto esquerdo','Dobre o canto superior esquerdo para dentro até que sua borda superior encontre a marca central.'],
    fold_right_corner:['Dobre o canto direito','Dobre o canto superior direito para dentro até que sua borda superior encontre a marca central. A parte de cima agora forma uma ponta.'],
    narrow_left_side:['Estreite o lado esquerdo','Dobre a borda inclinada superior esquerda para dentro até encontrar a marca central.'],
    narrow_right_side:['Estreite o lado direito','Dobre a borda inclinada superior direita para dentro até encontrar a marca central.'],
    close_body:['Feche o corpo do avião','Dobre o avião ao meio ao longo da marca central, deixando as dobras anteriores para dentro. Coloque-o de lado com o nariz apontado para longe de você.'],
    fold_first_wing:['Dobre a primeira asa','Dobre a asa exposta para baixo até que sua borda longa e inclinada se alinhe com a borda inferior do corpo. Mantenha essa asa dobrada para a próxima foto.'],
    fold_second_wing:['Finalize a segunda asa','Vire o avião e dobre a outra asa da mesma forma. Abra um pouco as duas asas para que o avião fique pronto para voar.'],
  },
};
let language;
try { language = localStorage.getItem('origami-language'); } catch (_) {}
if (!['en','pt-BR'].includes(language)) language = navigator.language.toLowerCase().startsWith('pt') ? 'pt-BR' : 'en';
function t(key, values = {}) {
  let value = (language === 'pt-BR' ? PT_BR[key] : EN[key]) ?? EN[key] ?? key;
  for (const [name, replacement] of Object.entries(values)) value = value.replaceAll(`{${name}}`, replacement);
  return value;
}
function translateError(message) {
  const match = message.match(/^Need at least (\d+) training samples for every action, after holdout: (.+)$/);
  if (language === 'pt-BR' && match) return `São necessárias pelo menos ${match[1]} amostras de treinamento para cada ação após reservar o participante de avaliação: ${match[2].split(', ').map(actionTitle).join(', ')}`;
  return t(message);
}
function actionTitle(id) {
  return language === 'pt-BR' && PAPER_PT.steps[id] ? PAPER_PT.steps[id][0] : experiment?.steps.find(s => s.action_id === id)?.title ?? id;
}
function stepText(step, field) {
  if (language === 'pt-BR' && PAPER_PT.steps[step.action_id]) return PAPER_PT.steps[step.action_id][field === 'title' ? 0 : 1];
  return step[field];
}
const originalNodes = new WeakMap();
function localizeStatic() {
  document.documentElement.lang = language;
  document.title = t('Fold / Learn');
  // Only marked copy is traversed, so current inputs and dynamic state survive a switch.
  for (const element of document.querySelectorAll('[data-i18n]')) {
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (!originalNodes.has(node)) originalNodes.set(node, node.textContent);
      const original = originalNodes.get(node), key = original.trim();
      if (key) node.textContent = original.replace(key, t(key));
    }
  }
  for (const element of document.querySelectorAll('[data-i18n-alt]')) element.alt = t(element.dataset.i18nAlt);
  document.getElementById('experiment-name').textContent = language === 'pt-BR' ? PAPER_PT.name : experiment?.name ?? '';
  document.getElementById('experiment-introduction').textContent = language === 'pt-BR' ? PAPER_PT.introduction : experiment?.introduction ?? '';
  document.getElementById('language').value = language;
}
