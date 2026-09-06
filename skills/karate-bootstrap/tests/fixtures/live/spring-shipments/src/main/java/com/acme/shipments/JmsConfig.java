package com.acme.shipments;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import java.util.Map;
import org.apache.qpid.jms.JmsConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.converter.MessageConversionException;
import org.springframework.jms.support.converter.MessageConverter;

/** AMQP 1.0 over Qpid JMS, the protocol the real services speak (design spec 11). */
@Configuration
public class JmsConfig {
    @Bean
    ConnectionFactory connectionFactory(@Value("${amq.url}") String url,
                                        @Value("${amq.user}") String user,
                                        @Value("${amq.password}") String password) {
        JmsConnectionFactory factory = new JmsConnectionFactory(url);
        factory.setUsername(user);
        factory.setPassword(password);
        return factory;
    }

    /**
     * Plain JSON text messages, no {@code __TypeId__} header: the harness's own {@code Jms}
     * helper (spec 5.5) publishes and reads {@link TextMessage}s the same way, so both sides
     * must agree on the wire format without Java type metadata.
     */
    @Bean
    MessageConverter jsonMessageConverter(ObjectMapper objectMapper) {
        return new MessageConverter() {
            @Override
            public Message toMessage(Object object, Session session) throws JMSException {
                try {
                    return session.createTextMessage(objectMapper.writeValueAsString(object));
                } catch (Exception e) {
                    throw new MessageConversionException("cannot convert to JSON", e);
                }
            }

            @Override
            public Object fromMessage(Message message) throws JMSException {
                if (!(message instanceof TextMessage textMessage)) {
                    throw new MessageConversionException("expected a TextMessage");
                }
                try {
                    return objectMapper.readValue(textMessage.getText(), Map.class);
                } catch (Exception e) {
                    throw new MessageConversionException("cannot parse JSON", e);
                }
            }
        };
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory, MessageConverter jsonMessageConverter) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setMessageConverter(jsonMessageConverter);
        return template;
    }
}
