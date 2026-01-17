import React from 'react';
import { ArrowLeft } from 'lucide-react';

const OfferPage = ({ onBack }) => {
    return (
        <div className="p-4 max-w-2xl mx-auto pb-32">
            <div className="flex items-center gap-3 mb-6">
                <button onClick={onBack} className="text-slate-400 hover:text-slate-600">
                    <ArrowLeft size={24} />
                </button>
                <h1 className="text-2xl font-black text-slate-800">Публичная Оферта</h1>
            </div>
            
            <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 space-y-6">
                {/* Header */}
                <div className="text-center pb-4 border-b border-slate-200">
                    <h2 className="text-xl font-black text-slate-900 mb-2">ЛИЦЕНЗИОННЫЙ ДОГОВОР-ОФЕРТА</h2>
                    <p className="text-sm text-slate-600 mb-1">на предоставление права использования программного обеспечения «JuicyStat»</p>
                    <p className="text-xs text-slate-500">г. Москва</p>
                    <p className="text-xs text-slate-500 font-medium mt-2">Редакция от 17.01.2026</p>
                </div>

                {/* Intro */}
                <div className="text-sm text-slate-700 leading-relaxed space-y-3">
                    <p>
                        Индивидуальный предприниматель <strong>Щербаков Антон Алексеевич</strong>, действующий на 
                        основании Свидетельства о государственной регистрации (ОГРНИП: <strong>325710000062103</strong>, 
                        ИНН: <strong>712807221159</strong>), именуемый в дальнейшем <strong>«Лицензиар»</strong>, публикует настоящую 
                        Публичную оферту (далее — <strong>«Договор»</strong>) о предоставлении права использования 
                        (простой неисключительной лицензии) программы для ЭВМ «JuicyStat».
                    </p>
                    <p>
                        Настоящий Договор является публичной офертой в соответствии со ст. 437 
                        Гражданского Кодекса Российской Федерации (ГК РФ). Акцептом (принятием) оферты 
                        является совершение действий, указанных в разделе 3 настоящего Договора.
                    </p>
                </div>

                {/* Section 1 */}
                <section className="space-y-3">
                    <h3 className="text-base font-black text-slate-900">1. Термины и определения</h3>
                    <div className="space-y-2 text-sm text-slate-700 leading-relaxed">
                        <p><strong>1.1. Сервис (ПО, Программа)</strong> — программа для ЭВМ «JuicyStat», реализованная в виде 
                        Telegram Mini App, предназначенная для аналитики продаж на маркетплейсе Wildberries, 
                        доступ к которой предоставляется Лицензиаром.</p>
                        
                        <p><strong>1.2. Лицензиат (Пользователь)</strong> — любое физическое лицо, индивидуальный 
                        предприниматель или юридическое лицо, принявшее условия настоящей Оферты.</p>
                        
                        <p><strong>1.3. Личный кабинет</strong> — интерфейс Сервиса в Telegram, позволяющий Лицензиату 
                        управлять настройками, добавлять API-ключи и просматривать аналитику.</p>
                        
                        <p><strong>1.4. API-ключ (Токен)</strong> — уникальный идентификатор, предоставляемый маркетплейсом 
                        Wildberries, который Лицензиат передает в Сервис для получения аналитических 
                        данных.</p>
                        
                        <p><strong>1.5. Тариф</strong> — стоимость и условия предоставления права использования Сервиса за 
                        определенный период времени или объем функционала.</p>
                    </div>
                </section>

                {/* Section 2 */}
                <section className="space-y-3">
                    <h3 className="text-base font-black text-slate-900">2. Предмет Договора</h3>
                    <div className="space-y-2 text-sm text-slate-700 leading-relaxed">
                        <p><strong>2.1.</strong> Лицензиар предоставляет Лицензиату право использования (простую 
                        неисключительную лицензию) Сервиса «JuicyStat» в пределах его функциональных 
                        возможностей путем предоставления удаленного доступа через сеть Интернет (SaaS), а 
                        Лицензиат обязуется оплачивать Лицензионное вознаграждение в соответствии с 
                        выбранным Тарифом.</p>
                        
                        <p><strong>2.2.</strong> Территория использования Сервиса: Российская Федерация и другие страны, где 
                        доступен сервис Telegram и сеть Интернет.</p>
                        
                        <p><strong>2.3.</strong> Лицензия предоставляется на срок действия оплаченного периода подписки.</p>
                    </div>
                </section>

                {/* Section 3 */}
                <section className="space-y-3">
                    <h3 className="text-base font-black text-slate-900">3. Акцепт Оферты</h3>
                    <div className="space-y-2 text-sm text-slate-700 leading-relaxed">
                        <p><strong>3.1.</strong> Акцептом настоящей Оферты является выполнение Лицензиатом любого из 
                        следующих действий:</p>
                        <ul className="list-disc list-inside space-y-1 ml-4">
                            <li>Прохождение процедуры регистрации (авторизации) в Сервисе через Telegram.</li>
                            <li>Оплата Лицензионного вознаграждения (подписки) согласно выбранному Тарифу.</li>
                            <li>Фактическое начало использования Сервиса (загрузка API-ключа).</li>
                        </ul>
                        <p><strong>3.2.</strong> Совершая Акцепт, Лицензиат подтверждает, что он полностью ознакомлен и 
                        согласен с условиями настоящего Договора и Политики конфиденциальности.</p>
                    </div>
                </section>

                {/* Section 4 */}
                <section className="space-y-3">
                    <h3 className="text-base font-black text-slate-900">4. Права и обязанности сторон</h3>
                    <div className="space-y-2 text-sm text-slate-700 leading-relaxed">
                        <p><strong>4.1. Лицензиар обязан:</strong></p>
                        <ul className="list-disc list-inside space-y-1 ml-4">
                            <li>Предоставить Лицензиату доступ к Сервису не позднее 24 часов с момента оплаты.</li>
                            <li>Предпринимать разумные технические меры для обеспечения стабильной работы Сервиса.</li>
                        </ul>
                        <p><strong>4.2. Лицензиат обязан:</strong></p>
                        <ul className="list-disc list-inside space-y-1 ml-4">
                            <li>Своевременно оплачивать Лицензионное вознаграждение.</li>
                            <li>Не использовать Сервис для противоправных действий.</li>
                            <li>Самостоятельно обеспечивать сохранность и конфиденциальность своего доступа к Telegram и API-ключей.</li>
                        </ul>
                    </div>
                </section>

                {/* Section 5 */}
                <section className="space-y-3">
                    <h3 className="text-base font-black text-slate-900">5. Ответственность и ограничение ответственности (Disclaimer)</h3>
                    <div className="space-y-2 text-sm text-slate-700 leading-relaxed">
                        <p><strong>5.1. Отказ от ответственности за действия третьих лиц (Wildberries):</strong></p>
                        <p>Сервис «JuicyStat» является независимым программным продуктом и не аффилирован, 
                        не спонсируется и не связан с компанией Wildberries (ООО «Вайлдберриз»). 
                        Лицензиар не несет ответственности за:</p>
                        <ul className="list-disc list-inside space-y-1 ml-4">
                            <li>Любые блокировки личного кабинета Лицензиата на маркетплейсе Wildberries.</li>
                            <li>Штрафы, наложенные маркетплейсом.</li>
                            <li>Изменения в работе API Wildberries, которые могут привести к временной или полной неработоспособности Сервиса.</li>
                            <li>Финансовые потери, упущенную выгоду и ли иной ущерб, возникший в результате использования или невозможности использования аналитических данных Сервиса.</li>
                        </ul>
                        <p><strong>5.2.</strong> Сервис предоставляется на условиях <strong>«как есть» (as is)</strong>. Лицензиар не гарантирует, 
                        что функционал Сервиса будет отвечать всем ожиданиям Лицензиата или что работа 
                        Сервиса будет бесперебойной и безошибочной.</p>
                        <p><strong>5.3. Ответственность за API-ключи:</strong></p>
                        <p>Лицензиат несет полную и единоличную ответственность за сохранность своих API- 
                        ключей. Лицензиат осознает риски, связанные с передачей API-ключей третьим лицам 
                        (включая Сервис), и принимает их на себя.</p>
                    </div>
                </section>

                {/* Section 6 */}
                <section className="space-y-3">
                    <h3 className="text-base font-black text-slate-900">6. Финансовые условия и порядок возврата средств</h3>
                    <div className="space-y-2 text-sm text-slate-700 leading-relaxed">
                        <p><strong>6.1.</strong> Размер Лицензионного вознаграждения определяется Тарифами, опубликованными 
                        в интерфейсе Сервиса.</p>
                        <p><strong>6.2.</strong> Оплата производится на условиях 100% предоплаты.</p>
                        <p><strong>6.3. Политика возврата (Refund Policy):</strong></p>
                        <ul className="list-disc list-inside space-y-1 ml-4">
                            <li>В случае отказа Лицензиата от использования Сервиса до истечения оплаченного 
                            периода, перерасчет и возврат денежных средств за неиспользованные дни/месяцы не производится.</li>
                            <li>Возврат средств возможен только в случае, если Сервис был полностью 
                            недоступен по вине Лицензиара более 48 часов подряд, и только за период простоя.</li>
                        </ul>
                    </div>
                </section>

                {/* Section 7 */}
                <section className="space-y-3">
                    <h3 className="text-base font-black text-slate-900">7. Интеллектуальная собственность</h3>
                    <div className="space-y-2 text-sm text-slate-700 leading-relaxed">
                        <p><strong>7.1.</strong> Исключительные права на Программу «JuicyStat», ее исходный код, дизайн и базы 
                        данных принадлежат Лицензиару.</p>
                        <p><strong>7.2.</strong> Лицензиату не предоставляются права на модификацию, декомпиляцию, 
                        дизассемблирование или создание производных продуктов на основе Сервиса.</p>
                    </div>
                </section>

                {/* Section 8 */}
                <section className="space-y-3">
                    <h3 className="text-base font-black text-slate-900">8. Срок действия и изменение условий</h3>
                    <div className="space-y-2 text-sm text-slate-700 leading-relaxed">
                        <p><strong>8.1.</strong> Договор вступает в силу с момента Акцепта и действует до момента расторжения.</p>
                        <p><strong>8.2.</strong> Лицензиар имеет право в одностороннем порядке вносить изменения в Договор и 
                        Тарифы. Изменения вступают в силу с момента их публикации в Сервисе. Продолжение 
                        использования Сервиса после публикации изменений означает согласие Лицензиата с ними.</p>
                    </div>
                </section>

                {/* Section 9 */}
                <section className="space-y-3">
                    <h3 className="text-base font-black text-slate-900">9. Разрешение споров</h3>
                    <div className="space-y-2 text-sm text-slate-700 leading-relaxed">
                        <p><strong>9.1.</strong> Все споры решаются путем переговоров. Претензионный порядок обязателен. Срок 
                        ответа на претензию — 10 рабочих дней.</p>
                        <p><strong>9.2.</strong> В случае недостижения согласия спор передается на рассмотрение в суд по месту 
                        нахождения Лицензиара.</p>
                    </div>
                </section>

                {/* Section 10 */}
                <section className="space-y-3 pt-4 border-t border-slate-200">
                    <h3 className="text-base font-black text-slate-900">10. Реквизиты Лицензиара</h3>
                    <div className="space-y-1 text-sm text-slate-700 leading-relaxed">
                        <p><strong>Индивидуальный предприниматель Щербаков Антон Алексеевич</strong></p>
                        <p>ИНН: <strong>712807221159</strong></p>
                        <p>ОГРНИП: <strong>325710000062103</strong></p>
                        <p>Email для связи: <a href="mailto:anton.sherbakov.01@gmail.com" className="text-indigo-600 hover:underline">anton.sherbakov.01@gmail.com</a></p>
                        <p>Служба поддержки Telegram: <a href="https://t.me/AAntonShch" target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">@AAntonShch</a></p>
                    </div>
                </section>
            </div>
        </div>
    );
};

export default OfferPage;
